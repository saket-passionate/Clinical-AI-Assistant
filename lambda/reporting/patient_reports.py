"""
AWS Lambda handler for generating patient clinical reports.

This module processes HealthScribe output from S3, generates HTML reports,
creates receipts for the application, and sends email notifications to patients.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


# Constants
DEFAULT_PATIENT_ID = "N/A"
DEFAULT_PATIENT_NAME = "Patient"
DEFAULT_VISIT_DATE = "N/A"
INPUT_PREFIX = "input"
REPORTS_PREFIX = "patient-reports"
RECEIPT_FILENAME = "receipt.json"
SUMMARY_FILENAME = "summary.html"

# Section name mappings
SECTION_TITLES = {
    "CHIEF_COMPLAINT": "Chief Complaint",
    "HISTORY_OF_PRESENT_ILLNESS": "History of Present Illness",
    "PHYSICAL_EXAMINATION": "Physical Examination",
    "ASSESSMENT": "Assessment & Diagnosis",
    "PLAN_OF_TREATMENT": "Treatment Plan",
    "MEDICATIONS": "Medications",
    "FAMILY_HISTORY": "Family History",
    "SOCIAL_HISTORY": "Social History",
    "REVIEW_OF_SYSTEMS": "Review of Systems"
}

# AWS Clients
s3_client = boto3.client("s3")
ses_client = boto3.client("ses")
transcribe_client = boto3.client("transcribe")


@dataclass
class PatientInfo:
    """Data class for patient information."""
    patient_id: str
    patient_name: str
    patient_email: str
    recording_id: str
    visit_date: str


@dataclass
class S3EventRecord:
    """Data class for S3 event record details."""
    bucket: str
    key: str


def text_to_bullets(text: str) -> str:
    """
    Convert text to HTML bullet list.
    
    Args:
        text: Plain text to convert
        
    Returns:
        HTML unordered list string
    """
    if not text:
        return ""

    parts = [
        p.strip()
        for p in text.replace(" - ", ". ").split(".")
        if p.strip()
    ]

    items = "".join(f"<li>{p}</li>" for p in parts)
    return f"<ul class='bullet-list'>{items}</ul>"


def text_to_numbered(text: str) -> str:
    """
    Convert text to HTML numbered list.
    
    Args:
        text: Plain text to convert
        
    Returns:
        HTML ordered list string
    """
    if not text:
        return ""

    parts = [p.strip() for p in text.split(".") if p.strip()]
    items = "".join(f"<li>{p}</li>" for p in parts)
    return f"<ol class='numbered-list'>{items}</ol>"


def generate_html_styles() -> str:
    """
    Generate CSS styles for the HTML report.
    
    Returns:
        CSS style string
    """
    return """
body {
    font-family: Arial, Helvetica, sans-serif;
    background-color: #F8FAFC;
    max-width: 800px;
    margin: auto;
    padding: 20px;
    color: #0F172A;
}

.header {
    background: linear-gradient(135deg, #2563EB, #1D4ED8);
    color: white;
    padding: 30px;
    border-radius: 10px;
    margin-bottom: 30px;
}

.header h1 {
    margin: 0 0 10px 0;
}

.patient-info {
    display: flex;
    gap: 20px;
    font-size: 14px;
}

.patient-badge {
    background: rgba(255,255,255,0.2);
    padding: 5px 12px;
    border-radius: 5px;
    font-weight: bold;
}

.section {
    background: white;
    padding: 22px;
    margin-bottom: 20px;
    border-radius: 8px;
    border-left: 4px solid #2563EB;
}

.section-title {
    color: #2563EB;
    font-size: 17px;
    font-weight: bold;
    margin-bottom: 12px;
    text-transform: uppercase;
}

.section-content {
    color: #334155;
    font-size: 15px;
}

.bullet-list {
    padding-left: 20px;
    margin: 0;
}

.bullet-list li {
    margin-bottom: 6px;
}

.numbered-list {
    padding-left: 22px;
}

.footer-note {
    background: #FEF3C7;
    border-left: 4px solid #F59E0B;
    padding: 15px;
    margin-top: 30px;
    border-radius: 5px;
    font-size: 13px;
}

.footer {
    text-align: center;
    margin-top: 30px;
    font-size: 13px;
    color: #64748B;
}
"""


def build_section_html(section: Dict[str, Any]) -> str:
    """
    Build HTML for a single clinical section.
    
    Args:
        section: Section dictionary from HealthScribe output
        
    Returns:
        HTML string for the section, or empty string if no content
    """
    section_name = section.get("SectionName", "")
    summary = section.get("Summary", [])

    if not summary:
        return ""

    title = SECTION_TITLES.get(
        section_name,
        section_name.replace("_", " ").title()
    )

    raw_text = " ".join(
        s.get("SummarizedSegment", "") for s in summary
    ).strip()

    if not raw_text:
        return ""

    # Treatment plan gets numbered steps, everything else bullets
    if section_name == "PLAN_OF_TREATMENT":
        content = text_to_numbered(raw_text)
    else:
        content = text_to_bullets(raw_text)

    return f"""
<div class="section">
    <div class="section-title">{title}</div>
    <div class="section-content">{content}</div>
</div>
"""


def build_patient_report(sections: List[Dict[str, Any]], patient_info: PatientInfo) -> str:
    """
    Build complete HTML patient report.
    
    Args:
        sections: List of clinical documentation sections from HealthScribe
        patient_info: Patient information data class
        
    Returns:
        Complete HTML report as string
    """
    html_header = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Clinical Visit Summary - {patient_info.patient_name}</title>
<style>
{generate_html_styles()}
</style>
</head>
<body>

<div class="header">
    <h1>Clinical Visit Summary</h1>
    <div class="patient-info">
        <div><strong>Patient:</strong> {patient_info.patient_name}</div>
        <div class="patient-badge">{patient_info.patient_id}</div>
        <div><strong>Date:</strong> {patient_info.visit_date}</div>
    </div>
</div>
"""

    # Build all sections
    sections_html = "".join(build_section_html(section) for section in sections)

    html_footer = """
<div class="footer-note">
<strong>Note:</strong> This is an AI-generated summary for your convenience.
Please review and verify all information.
</div>

<div class="footer">
<p><strong>MediVoice AI</strong> – Clinical Documentation Assistant</p>
<p>Generated using AWS HealthScribe</p>
<p>© 2026 All rights reserved</p>
</div>

</body>
</html>
"""

    return html_header + sections_html + html_footer


def extract_s3_event_record(event: Dict[str, Any]) -> S3EventRecord:
    """
    Extract S3 event record details.
    
    Args:
        event: S3 event notification dictionary
        
    Returns:
        S3EventRecord with bucket and key
        
    Raises:
        KeyError: If required fields are missing
    """
    try:
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        return S3EventRecord(bucket=bucket, key=key)
    except KeyError as e:
        raise ValueError(f"Invalid S3 event structure: missing field {e}")


def convert_tags_to_dict(tags_list: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Convert AWS tags list to dictionary.
    
    Args:
        tags_list: List of tag dictionaries with 'Key' and 'Value'
        
    Returns:
        Dictionary mapping tag keys to values
    """
    return {tag["Key"]: tag["Value"] for tag in tags_list}


def extract_audio_metadata(bucket: str, media_uri: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract metadata from original audio file.
    
    Args:
        bucket: S3 bucket name
        media_uri: S3 URI of the audio file
        
    Returns:
        Tuple of (visit_id, patient_id), both may be None if extraction fails
    """
    try:
        # Extract audio key from URI: s3://bucket/input/PAT-0012/VIS-20260205-0005/audio.webm
        audio_key = media_uri.replace(f"s3://{bucket}/", "")
        
        head = s3_client.head_object(Bucket=bucket, Key=audio_key)
        metadata = head.get("Metadata", {})
        
        visit_id = metadata.get("visit-id")
        patient_id = metadata.get("patient-id")
        
        print(f"✓ Extracted metadata - visit_id: {visit_id}, patient_id: {patient_id}")
        return visit_id, patient_id
        
    except ClientError as e:
        print(f"⚠ Could not read audio metadata: {e}")
        return None, None


def get_patient_info_from_job(job_name: str, bucket: str) -> tuple[PatientInfo, Optional[str], Optional[str]]:
    """
    Retrieve patient information from HealthScribe job tags and metadata.
    
    Args:
        job_name: HealthScribe job name
        bucket: S3 bucket name
        
    Returns:
        Tuple of (PatientInfo, visit_id, patient_id)
    """
    try:
        job_response = transcribe_client.get_medical_scribe_job(
            MedicalScribeJobName=job_name
        )
        job = job_response["MedicalScribeJob"]
        
        # Convert tags list to dictionary
        tags_list = job.get("Tags", [])
        tags = convert_tags_to_dict(tags_list)
        
        completion = job.get("CompletionTime")
        visit_date = str(completion).split("T")[0] if completion else DEFAULT_VISIT_DATE

        patient_info = PatientInfo(
            patient_id=tags.get("patient_id", DEFAULT_PATIENT_ID),
            patient_name=tags.get("patient_name", DEFAULT_PATIENT_NAME),
            patient_email=tags.get("patient_email", ""),
            recording_id=tags.get("recording_id", ""),
            visit_date=visit_date
        )
        
        # Try to get visit_id and patient_id from audio metadata
        visit_id, patient_id = None, None
        media_uri = job.get("Media", {}).get("MediaFileUri", "")
        
        if media_uri:
            visit_id, patient_id = extract_audio_metadata(bucket, media_uri)
            
            # If we got audio metadata, try to get additional patient info
            if media_uri:
                try:
                    audio_key = media_uri.replace(f"s3://{bucket}/", "")
                    head = s3_client.head_object(Bucket=bucket, Key=audio_key)
                    metadata = head.get("Metadata", {})
                    
                    if metadata.get("patient-email"):
                        patient_info.patient_email = metadata.get("patient-email")
                    if metadata.get("patient-name"):
                        patient_info.patient_name = metadata.get("patient-name").replace("-", " ")
                except ClientError:
                    pass  # Already logged in extract_audio_metadata
        
        return patient_info, visit_id, patient_id
        
    except ClientError as e:
        print(f"⚠ Error getting job info: {e}")
        return PatientInfo(
            patient_id=DEFAULT_PATIENT_ID,
            patient_name=DEFAULT_PATIENT_NAME,
            patient_email="",
            recording_id="",
            visit_date=DEFAULT_VISIT_DATE
        ), None, None


def load_clinical_documentation(bucket: str, key: str) -> List[Dict[str, Any]]:
    """
    Load clinical documentation sections from S3.
    
    Args:
        bucket: S3 bucket name
        key: S3 object key for summary.json
        
    Returns:
        List of clinical documentation sections
        
    Raises:
        ClientError: If S3 read fails
    """
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    data = json.loads(obj["Body"].read())
    return data["ClinicalDocumentation"]["Sections"]


def save_html_report(bucket: str, job_name: str, report_html: str) -> str:
    """
    Save HTML report to S3.
    
    Args:
        bucket: S3 bucket name
        job_name: HealthScribe job name
        report_html: HTML report content
        
    Returns:
        S3 key where report was saved
        
    Raises:
        ClientError: If S3 write fails
    """
    report_key = f"{REPORTS_PREFIX}/{job_name}/{SUMMARY_FILENAME}"
    
    s3_client.put_object(
        Bucket=bucket,
        Key=report_key,
        Body=report_html.encode("utf-8"),
        ContentType="text/html"
    )
    
    print(f"✓ Saved report to: {report_key}")
    return report_key


def create_receipt(
    bucket: str,
    patient_id: str,
    visit_id: str,
    report_key: str,
    job_name: str
) -> Optional[str]:
    """
    Create receipt.json file for the application.
    
    Args:
        bucket: S3 bucket name
        patient_id: Patient identifier
        visit_id: Visit identifier
        report_key: S3 key of the generated report
        job_name: HealthScribe job name
        
    Returns:
        S3 key where receipt was saved, or None if patient/visit IDs missing
    """
    if not visit_id or not patient_id:
        print(f"⚠ Cannot create receipt - visit_id: {visit_id}, patient_id: {patient_id}")
        return None
    
    receipt = {
        "status": "COMPLETED",
        "report_path": report_key,
        "job_name": job_name,
        "completed_at": datetime.utcnow().isoformat() + "Z"
    }
    
    receipt_key = f"{INPUT_PREFIX}/{patient_id}/{visit_id}/{RECEIPT_FILENAME}"
    
    s3_client.put_object(
        Bucket=bucket,
        Key=receipt_key,
        Body=json.dumps(receipt),
        ContentType="application/json"
    )
    
    print(f"✓ Created receipt at: {receipt_key}")
    return receipt_key


def send_patient_email(patient_info: PatientInfo, report_html: str) -> None:
    """
    Send email notification to patient with report.
    
    Args:
        patient_info: Patient information
        report_html: HTML report content
        
    Raises:
        ClientError: If SES send fails
    """
    if not patient_info.patient_email:
        print("⚠ No patient email address - skipping email notification")
        return
    
    source_email = os.environ.get("SOURCE_EMAIL")
    if not source_email:
        print("⚠ SOURCE_EMAIL environment variable not set - skipping email")
        return
    
    ses_client.send_email(
        Source=source_email,
        Destination={"ToAddresses": [patient_info.patient_email]},
        Message={
            "Subject": {
                "Data": f"Your Visit Summary - {patient_info.patient_name}"
            },
            "Body": {
                "Html": {"Data": report_html}
            }
        }
    )
    
    print(f"✓ Sent email to: {patient_info.patient_email}")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating patient reports from HealthScribe output.
    
    Triggered by S3 event notification when HealthScribe writes summary.json.
    Generates HTML report, creates receipt for the app, and sends email to patient.
    
    Expected S3 Event Structure:
    {
        "Records": [{
            "s3": {
                "bucket": {"name": "bucket-name"},
                "object": {"key": "hs-PAT-0012-Name-20260205/summary.json"}
            }
        }]
    }
    
    Args:
        event: S3 event notification dictionary
        context: Lambda context object
        
    Returns:
        Dictionary with status and generated file keys
        
    Raises:
        ValueError: If event structure is invalid
        ClientError: If AWS API calls fail
    """
    print("Event received:", json.dumps(event))
    
    # Extract S3 event details
    record = extract_s3_event_record(event)
    print(f"Processing: bucket={record.bucket}, key={record.key}")
    
    # Extract job name from key (e.g., hs-PAT-0012-Name-20260205/summary.json)
    job_name = record.key.split("/")[0]
    
    # Get patient information from HealthScribe job
    patient_info, visit_id, patient_id = get_patient_info_from_job(job_name, record.bucket)
    
    # Load clinical documentation
    sections = load_clinical_documentation(record.bucket, record.key)
    
    # Generate HTML report
    report_html = build_patient_report(sections, patient_info)
    
    # Save report to S3
    report_key = save_html_report(record.bucket, job_name, report_html)
    
    # Create receipt for the application
    receipt_key = create_receipt(
        bucket=record.bucket,
        patient_id=patient_id,
        visit_id=visit_id,
        report_key=report_key,
        job_name=job_name
    )
    
    # Send email to patient
    try:
        send_patient_email(patient_info, report_html)
    except ClientError as e:
        print(f"⚠ Failed to send email: {e}")
        # Don't fail the entire function if email fails
    
    return {
        "status": "Report generated",
        "report_key": report_key,
        "receipt_key": receipt_key
    }
