"""
AWS Lambda handler for processing medical audio files and starting HealthScribe jobs.

This module handles EventBridge triggers when new audio files are uploaded to S3,
extracts patient metadata, and initiates AWS HealthScribe transcription jobs.
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError


# Constants
INPUT_PREFIX = "input/"
DEFAULT_PATIENT_ID = "UNKNOWN"
DEFAULT_PATIENT_NAME = "Unknown"
JOB_NAME_PREFIX = "hs"
NOTE_TEMPLATE = "PHYSICAL_SOAP"
CLINICIAN_CHANNEL = 0
PATIENT_CHANNEL = 1

# AWS Clients
s3_client = boto3.client("s3")
healthscribe_client = boto3.client("transcribe")


@dataclass
class PatientMetadata:
    """Data class for patient metadata."""
    patient_id: str
    patient_name: str
    patient_email: str
    recording_id: str


@dataclass
class EventDetail:
    """Data class for EventBridge event details."""
    bucket: str
    key: str


def extract_event_details(event: Dict[str, Any]) -> EventDetail:
    """
    Extract bucket and key from EventBridge event.
    
    Args:
        event: EventBridge event dictionary
        
    Returns:
        EventDetail object containing bucket and key
        
    Raises:
        KeyError: If required fields are missing from event
    """
    try:
        detail = event['detail']
        bucket = detail['bucket']['name']
        key = detail['object']['key']
        return EventDetail(bucket=bucket, key=key)
    except KeyError as e:
        raise ValueError(f"Invalid event structure: missing field {e}")


def extract_metadata_from_s3(bucket: str, key: str) -> PatientMetadata:
    """
    Extract patient metadata from S3 object metadata.
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        PatientMetadata object with extracted information
    """
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        metadata = response.get('Metadata', {})
        
        patient_id = metadata.get('patient-id', DEFAULT_PATIENT_ID)
        patient_name = metadata.get('patient-name', DEFAULT_PATIENT_NAME).replace('-', ' ')
        patient_email = metadata.get('patient-email', '')
        recording_id = metadata.get('recording-id', '')
        
        print(f"✓ Metadata extracted:")
        print(f"  - Patient ID: {patient_id}")
        print(f"  - Patient Name: {patient_name}")
        print(f"  - Patient Email: {patient_email}")
        print(f"  - Recording ID: {recording_id}")
        
        return PatientMetadata(
            patient_id=patient_id,
            patient_name=patient_name,
            patient_email=patient_email,
            recording_id=recording_id
        )
        
    except ClientError as e:
        print(f"⚠ Error reading S3 metadata: {e}")
        return _fallback_metadata_from_key(key)


def _fallback_metadata_from_key(key: str) -> PatientMetadata:
    """
    Fallback method to extract metadata from filename when S3 metadata is unavailable.
    
    Args:
        key: S3 object key
        
    Returns:
        PatientMetadata with extracted or default values
    """
    filename = key.split('/')[-1]
    parts = filename.split('_')
    patient_id = parts[0] if parts else DEFAULT_PATIENT_ID
    
    print(f"⚠ Using fallback metadata from filename: {filename}")
    
    return PatientMetadata(
        patient_id=patient_id,
        patient_name=DEFAULT_PATIENT_NAME,
        patient_email='',
        recording_id=''
    )


def generate_job_name(patient_id: str, patient_name: str) -> str:
    """
    Generate a unique HealthScribe job name.
    
    Args:
        patient_id: Patient identifier
        patient_name: Patient name
        
    Returns:
        Formatted job name string
    """
    clean_name = re.sub(r'[^a-zA-Z0-9-]', '', patient_name.replace(' ', ''))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{JOB_NAME_PREFIX}-{patient_id}-{clean_name}-{timestamp}"


def create_healthscribe_tags(metadata: PatientMetadata) -> list:
    """
    Create tags list for HealthScribe job.
    
    Args:
        metadata: PatientMetadata object
        
    Returns:
        List of tag dictionaries
    """
    return [
        {'Key': 'patient_id', 'Value': metadata.patient_id},
        {'Key': 'patient_name', 'Value': metadata.patient_name},
        {'Key': 'patient_email', 'Value': metadata.patient_email},
        {'Key': 'recording_id', 'Value': metadata.recording_id}
    ]


def start_healthscribe_job(
    job_name: str,
    bucket: str,
    key: str,
    metadata: PatientMetadata
) -> Dict[str, str]:
    """
    Start AWS HealthScribe medical transcription job.
    
    Args:
        job_name: Unique job identifier
        bucket: S3 bucket containing audio file
        key: S3 object key for audio file
        metadata: Patient metadata
        
    Returns:
        Dictionary with job status and details
        
    Raises:
        ClientError: If HealthScribe job fails to start
    """
    job_uri = f"s3://{bucket}/{key}"
    role_arn = os.environ['TRANSCRIBE_ROLE_ARN']
    
    print(f"Starting HealthScribe job: {job_name}")
    print(f"Media URI: {job_uri}")
    
    healthscribe_client.start_medical_scribe_job(
        MedicalScribeJobName=job_name,
        DataAccessRoleArn=role_arn,
        Settings={
            'ChannelIdentification': True,
            'ClinicalNoteGenerationSettings': {
                'NoteTemplate': NOTE_TEMPLATE
            }
        },
        ChannelDefinitions=[
            {'ChannelId': CLINICIAN_CHANNEL, 'ParticipantRole': 'CLINICIAN'},
            {'ChannelId': PATIENT_CHANNEL, 'ParticipantRole': 'PATIENT'}
        ],
        Media={'MediaFileUri': job_uri},
        OutputBucketName=bucket,
        Tags=create_healthscribe_tags(metadata)
    )
    
    print(f"✓ Job started successfully: {job_name}")
    print(f"✓ Recording ID: {metadata.recording_id}")
    
    return {
        "status": "HealthScribe started",
        "job_name": job_name,
        "recording_id": metadata.recording_id,
        "patient_id": metadata.patient_id
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, str]:
    """
    Lambda handler for processing medical audio uploads.
    
    EventBridge triggers this Lambda when a new audio file is uploaded to S3.
    It starts a HealthScribe job with the audio file and metadata extracted 
    from S3 object tags.
    
    Expected EventBridge Event Structure:
    {
        "detail": {
            "version": "0",
            "bucket": {
                "name": "your-audio-bucket"
            },
            "object": {
                "key": "input/PAT-0012/VIS-20260205-0005/audio.webm",
                "size": 12345678,
                "eTag": "abcdef1234567890",
                "sequencer": "1234567890"
            }
        }
    }
    
    Args:
        event: EventBridge event dictionary
        context: Lambda context object
        
    Returns:
        Dictionary with job status and details
        
    Raises:
        ValueError: If event structure is invalid
        ClientError: If AWS API calls fail
    """
    print("Event received:", json.dumps(event))
    
    # Extract event details
    event_detail = extract_event_details(event)
    print(f"Processing file from bucket: {event_detail.bucket}, key: {event_detail.key}")
    
    # Only process files in the input prefix
    if not event_detail.key.startswith(INPUT_PREFIX):
        print(f"⚠ Skipping file - not in {INPUT_PREFIX} prefix")
        return {
            "status": "skipped",
            "reason": "File not in input directory"
        }
    
    try:
        # Extract metadata
        metadata = extract_metadata_from_s3(event_detail.bucket, event_detail.key)
        
        # Generate job name
        job_name = generate_job_name(metadata.patient_id, metadata.patient_name)
        
        # Start HealthScribe job
        result = start_healthscribe_job(
            job_name=job_name,
            bucket=event_detail.bucket,
            key=event_detail.key,
            metadata=metadata
        )
        
        return result
        
    except ClientError as e:
        error_msg = f"AWS API error: {e}"
        print(f"✗ {error_msg}")
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(f"✗ {error_msg}")
        raise

