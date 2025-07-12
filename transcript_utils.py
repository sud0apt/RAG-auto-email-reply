import requests
import openai
import logging
import re
import os
from fpdf import FPDF
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)

# Fireflies API Configuration
FIRELIES_API_URL = 'https://api.fireflies.ai/graphql'


def get_access_token(endpoint):
    """
    Returns the API token based on the endpoint user.
    """
    if endpoint == '/santiago/fireflies':
        return 'xxxx'
    elif endpoint == '/kyle/fireflies':
        return 'xxxx'
    elif endpoint == '/jackie/fireflies':
        return 'xxxx'
    else:
        raise ValueError("Invalid endpoint")


def fetch_transcript_details(meeting_id, api_key):
    """
    Fetch transcript details from Fireflies API.
    """
    query = """
    query Transcript($transcriptId: String!) {
        transcript(id: $transcriptId) {
            id
            title
            date
            meeting_attendees {
                email
            }
            sentences {
                speaker_name
                text
            }
        }
    }
    """
    variables = {"transcriptId": meeting_id}
    data = {"query": query, "variables": variables}

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    response = requests.post(FIRELIES_API_URL, headers=headers, json=data)
    logging.info(f"API Response: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        if 'errors' in result:
            logging.error(f"GraphQL Errors: {result['errors']}")
            return None
        return result.get('data', {}).get('transcript', {})
    else:
        logging.error(f"Failed to fetch transcript. Status code: {response.status_code}")
        return None


def process_transcript_content(transcript):
    """
    Process transcript sentences into readable format.
    """
    sentences = transcript.get('sentences', [])
    content = "\n\nTranscript:\n" 
    for sentence in sentences:
        speaker = sentence.get('speaker_name', 'Unknown Speaker')
        text = sentence.get('text', '')
        content += f"{speaker}: {text}\n\n"
    return content

def get_transcript_speakers(transcript):
    sentences = transcript.get('sentences', [])
    speakers = []
    for sentence in sentences:
        speaker = sentence.get('speaker_name', 'Unknown Speaker')
        if speaker not in speakers:
            speakers.append(speaker)
    return speakers

def save_transcript_as_pdf(transcript_details, content):
    """
    Save transcript details and content into a PDF file.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)

    title = transcript_details.get('title', 'Untitled Transcript')
    pdf.cell(200, 10, txt=f"Title: {title}", ln=True, align='C')

    date = transcript_details.get('date', 'No Date')
    pdf.cell(200, 10, txt=f"Date: {date}", ln=True, align='C')

    pdf.ln(10)
    pdf.cell(200, 10, txt="Transcript Content:", ln=True)
    pdf.multi_cell(0, 10, txt=content)

    filename = f"{title.replace(' ', '_')}.pdf"
    os.makedirs("transcripts", exist_ok=True)
    file_path = os.path.join("transcripts", filename)
    pdf.output(file_path)
    return file_path


def analyze_transcript_with_gpt(content, title):
    """
    Use GPT-4 to determine whether the meeting is worthwhile.
    """
    match = re.match(r".+ X .+", title)
    if match:
        logging.info("Rule 1 Passed: Title matches investor-client format.")
        return True, "Title matches investor-client format."

    prompt = f"""
    Analyze the following meeting transcript to determine if it is a worthwhile investor-client meeting.
    Transcript:
    {content[:4000]}  

    Guidelines:
    - Return "YES" if it is a worthwhile investor-client meeting.
    - Return "NO" if it is internal or unrelated.
    """
    try:
        client = openai.Client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an AI assistant analyzing transcripts."},
                {"role": "user", "content": prompt}
            ]
        )
        analysis = response.choices[0].message.content.strip()
        if "YES" in analysis.upper():
            logging.info("Rule 2 Passed: GPT analysis deemed the meeting worthwhile.")
            return True, analysis
        else:
            return False, analysis
    except Exception as e:
        logging.error(f"GPT Analysis Error: {e}")
        return False, f"Error analyzing transcript: {e}"
