import json
from flask import Flask, request, jsonify
import logging
import requests
import fitz  # PyMuPDF for PDF processing
import uuid  # For generating UUIDs as valid IDs
from RAG import RAGKBProcessor
from database_utils import get_meeting_details_and_notes_by_fuzzy_title
from outlook import send_email, get_access_token_outlook
from transcript_utils import *
import openai  # GPT API integration
from context_gathering import classify_context, role_identifier
from enum import Enum
import threading  # For handling request locks

# Flask Application
app = Flask(__name__)

# Logging Setup
logging.basicConfig(level=logging.WARNING)  # Only logs warnings and errors

# Initialize RAGKBProcessor
rag_processor = RAGKBProcessor()

# Thread lock to handle single POST request at a time
request_lock = threading.Lock()

# GPT API Key
OPENAI_API_KEY = 'xxxx'

def process_investor_report(report_url, meeting_id, title):
    """
    Download, extract text, and store the investor report in the RAG knowledge base.
    """
    try:
        # Step 1: Download the report
        response = requests.get(report_url)
        if response.status_code != 200:
            raise Exception(f"Failed to download report: {response.status_code}")

        # Step 2: Save locally
        local_path = f"investor_report_{meeting_id}.pdf"
        with open(local_path, "wb") as file:
            file.write(response.content)

        # Step 3: Extract text from PDF
        doc = fitz.open(local_path)
        content = ""
        for page in doc:
            content += page.get_text()

        # Step 4: Vectorize the investor report
        vectorize_data(content, "investor_report", meeting_id, title)

        return content  # Return extracted text for further processing

    except Exception as e:
        logging.error(f"Error processing investor report: {e}")
        return ""


def vectorize_data(data, source, meeting_id, title):
    """
    Vectorize and store data in Qdrant with specified source.
    """
    try:
        points = []
        chunks = rag_processor.chunk_text(data)  # Split data into chunks

        # Log data chunks
        logging.info(f"Vectorizing {source} with {len(chunks)} chunks.")

        for i, chunk in enumerate(chunks):
            # Generate valid UUID for point ID
            point_id = str(uuid.uuid4())
            embedding = rag_processor.st_model.encode(chunk).tolist()

            points.append({
                "id": point_id,
                "vector": embedding,
                "payload": {
                    "text": chunk,
                    "source": source,
                    "metadata": {"meeting_id": meeting_id, "title": title}
                }
            })

        # Insert points into Qdrant
        rag_processor.qdrant_client.upsert(collection_name="knowledge_base", points=points)
        logging.info(f"{source} vectorized successfully with {len(points)} chunks.")

    except Exception as e:
        logging.error(f"Error vectorizing {source}: {e}")


def check_with_gpt(content, keyword):
    """
    Use GPT API to determine if the meeting content mentions {keyword}.
    Handles large inputs by truncating content to fit GPT's token limit.
    """
    try:
        # Instantiate a new client for every request to ensure stateless interaction
        client = openai.OpenAI() 

        # GPT API Request with improved prompt
        prompt = f"""
        Analyze the following text to determine if it explicitly or implicitly refers to {keyword}. 
        Provide a clear and concise reasoning in your response.

        Text:
        {content}

        Guidelines:
        1. Focus only on mentions related to {keyword}.
        2. Ignore unrelated information or general context.
        3. If it refers to {keyword} indirectly, explain how it is implied.
        4. Respond 'YES' if the text contains any mention of {keyword}.
        5. Respond 'NO' if no mention is present, and explain why.
        """
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"You are an assistant analyzing text for mentions of {keyword}. DO NOT USE BACK ANY PREVIOUS INFORMATION OR ANSWERS"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300, 
            temperature=0.2
        )

        # Process GPT response
        gpt_reply = response.choices[0].message.content.strip()
        logging.info(f"GPT Analysis: {gpt_reply}")

        # Decision
        return "yes" in gpt_reply.lower(), gpt_reply

    except Exception as e:
        logging.error(f"Error querying GPT API: {e}")
        return False, f"Error: {str(e)}"
    
class FlowType(Enum):
    YES_NDA_YES_DR = "Data Room"
    YES_NDA_NO_DR_YES_PRENDA = "Pre-NDA"
    YES_NDA_NO_DR_NO_PRENDA = "NDA"
    NO_NDA_YES_DR = "Data room"
    NO_NDA_NO_DR_YES_PRENDA = "Pre-NDA"
    NO_NDA_NO_DR_NO_PRENDA = "No specific flow"

def logic_block(content,roles):
    """
    Check the type of workflow based on content and title.
    """
    nda_mentioned, nda_gpt_analysis, nda_retrieved_context = check_NDA(content)
    dataroom_mentioned, dataroom_gpt_analysis, dataroom_retrieved_context = check_dataroom(content)
    selected_flow = FlowType.NO_NDA_NO_DR_NO_PRENDA 

    if nda_mentioned:
        if dataroom_mentioned:
            logging.info("data room flow entered")
            selected_flow = FlowType.YES_NDA_YES_DR
            dataroom_flow(selected_flow,dataroom_retrieved_context,roles)
        else:
            prenda_mentioned, prenda_gpt_analysis, prenda_retrieved_context = check_prenda(content)
            if prenda_mentioned:
                logging.info("pre NDA flow entered")
                selected_flow = FlowType.YES_NDA_NO_DR_YES_PRENDA
                prenda_flow(selected_flow,prenda_retrieved_context,roles)

            else:
                logging.info("NDA facilitation flow entered")
                selected_flow = FlowType.YES_NDA_NO_DR_NO_PRENDA
                nda_flow(selected_flow,nda_retrieved_context,roles)
    else:
        if dataroom_mentioned:
            logging.info("data room flow entered")
            selected_flow = FlowType.NO_NDA_YES_DR
            dataroom_flow(selected_flow,dataroom_retrieved_context,roles)
        else:
            prenda_mentioned, prenda_gpt_analysis, prenda_retrieved_context = check_prenda(content)
            if prenda_mentioned:
                logging.info("pre NDA flow entered")
                selected_flow = FlowType.NO_NDA_NO_DR_YES_PRENDA
                prenda_flow(selected_flow,prenda_retrieved_context,roles)

            else:
                logging.info("No specific flow entered")
                

    return nda_mentioned, nda_gpt_analysis, dataroom_mentioned, dataroom_gpt_analysis, prenda_mentioned, prenda_gpt_analysis

def nda_flow(selected_flow, retrieved_context,roles):
    scenario = classify_context(selected_flow,retrieved_context,roles)
    
    # Use OpenAI to generate an email body
    email_body = generate_email_body(scenario, roles)

    recipient_email = 'xxxx'  
    subject = f"Follow-up on {scenario}" 

    # Send email using Outlook API
    token = get_access_token_outlook()  
    send_email(token, recipient_email, subject, email_body)

    logging.info("Email sent successfully!")

def prenda_flow(selected_flow, retrieved_context,roles):
    scenario = classify_context(selected_flow,retrieved_context,roles)

    # Use OpenAI to generate an email body
    email_body = generate_email_body(scenario, roles)

    recipient_email = 'xxxx'  
    subject = f"Follow-up on {scenario}" 

    # Send email using Outlook API
    token = get_access_token_outlook()  
    send_email(token, recipient_email, subject, email_body)

    logging.info("Email sent successfully!")

def dataroom_flow(selected_flow, retrieved_context,roles):
    scenario = classify_context(selected_flow,retrieved_context,roles)

    # Use OpenAI to generate an email body
    email_body = generate_email_body(scenario, roles)

    recipient_email = 'xxxx'  
    subject = f"Follow-up on {scenario}" 

    # Send email using Outlook API
    token = get_access_token_outlook()  
    send_email(token, recipient_email, subject, email_body)

    logging.info("Email sent successfully!")

def generate_email_body(scenario, roles):
    """
    Generates email content using GPT based on scenario and roles.
    """
    # Instantiate a new client for every request to prevent memory carryover
    client = openai.OpenAI()

    prompt = f"""
    Write a professional email based on the following scenario:

    Scenario:
    {scenario}

    Roles:
    {roles}

    Instructions:
    1. Address the email to the appropriate recipient based on the scenario (recipient is always almost the investor). Make sure to address them only by their first name like "Hi Darren," not "Hi Darren Williams".
    2. Provide a summary of the scenario and the next steps.
    3. Maintain a relaxed & friendly tone throughout the email.
    4. Make sure sender name is a speaker of facilitator role; if none, then default to Santiago Herrera (full name) from Outer Insights.
    5. Mention that the required document inferred from the scenario (e.g., NDA, Pre-NDA materials, or Data Room access) is **attached**.
    6. Use the following formats based on the scenario:
        - NDA: Mention that the NDA document from the scenario is attached for review and signature.
        - Data Room: Mention that the Data Room access details from the scenario are attached.
        - Pre-NDA: Mention that the requested Pre-NDA materials or supporting documents from the scenario are attached.
    7. Do not wrap with html but use the <h1> tag for the subject line and <p> tag for the content.
    8. Make the email concise and straight to the point.
    9. for the subject given an example json below only extract the "scenario" key value as text and use it as the subject line with Follow-up on appended to it. 
    10. dont say thanks for reaching out, since the context of this email is a follow up email to an initial call.

    json is "scenario": "Investor requests data room and Data Room", "reason": "The context indicates a request for documents, specifically a 'corporate deck,' made by Bruce Thomas [BTIG], identified as an 'Investor.' Since a 'corporate deck' can be considered part of a data room, this fits the 'Data Room' scenario.", "quote": "Bruce Thomas [BTIG]: I was unable to download the corporate deck for some reason on the Docsend link." 

    Format:
    <h1>Subject: Follow-up on {scenario}</h1>
    <p>Hi [Recipient],</p>
    <p>Body content goes here...</p>
    <p>Best,<br>[Sender Name (full)]</p>
    <p>Outer Insights</p>
    """

    try:

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an AI email assistant creating professional emails based on context. DO NOT USE BACK ANY PREVIOUS INFORMATION OR ANSWERS"},
                {"role": "user", "content": prompt}
            ]
        )

        # Extract and clean up email body
        email_body = response.choices[0].message.content.strip()

        # Ensure no additional formatting like HTML tags or code blocks
        email_body = email_body.replace("```html", "").replace("```", "").strip()

        return email_body

    except Exception as e:
        logging.error("Error generating email body: %s", e)
        return "<h1>Error generating email content.</h1><p>Please try again later.</p>"



def check_NDA(content):
    query = "NDA or Non-Disclosure Agreement"
    vectorized_results = rag_processor.search_context(query, top_k=3)
    retrieved_context = "\n".join([res['text'] for res in vectorized_results]) + "\n" + content
    keyword = "NDA (non-disclosure agreement)"

    nda_mentioned, nda_gpt_analysis = check_with_gpt(retrieved_context,keyword=keyword)
    return nda_mentioned, nda_gpt_analysis, retrieved_context

def check_dataroom(content):
    query = "data room or dataroom"
    vectorized_results = rag_processor.search_context(query, top_k=3)
    retrieved_context = "\n".join([res['text'] for res in vectorized_results]) + "\n" + content
    keyword = "data room"

    dataroom_mentioned, dataroom_gpt_analysis = check_with_gpt(retrieved_context,keyword=keyword)
    return dataroom_mentioned, dataroom_gpt_analysis, retrieved_context

def check_prenda(content):
    """
    Check for mentions of supporting documents or additional information related to pre-NDA flow.
    """
    query = "supporting documents or more information"
    vectorized_results = rag_processor.search_context(query, top_k=3)
    
    # Combine all retrieved contexts
    retrieved_context = "\n".join([res['text'] for res in vectorized_results]) + "\n" + content
    
    # Keyword analysis
    keyword = "supporting documents or more information for the company from the investor"
    prenda_mentioned, prenda_gpt_analysis = check_with_gpt(retrieved_context, keyword=keyword)

    # Return retrieved context along with results
    return prenda_mentioned, prenda_gpt_analysis, retrieved_context



@app.route('/<user>/fireflies', methods=['POST'])
def handle_webhook(user):
    """
    Webhook endpoint to process transcripts, meeting notes, investor reports, and check for NDA mentions.
    """
    # Acquire lock to process one request at a time
    if not request_lock.acquire(blocking=False):  # Non-blocking mode
        logging.warning("Another request is already being processed.")
        return jsonify({'error': 'Server is busy processing another request. Please try again later.'}), 429

    try:
        # Reset Qdrant collection for each POST request to clear any previous data
        rag_processor.reset_collection()  # Clears and recreates collection
        logging.info("Qdrant collection reset successfully.")

        # Clear variables for each POST request
        content = ""
        roles = []  
        notes = []
        meeting_details = {}
        investor_report = None

        # Step 1: Get API key based on user
        api_key = get_access_token(f'/{user}/fireflies')
        data = request.json

        # Step 2: Validate incoming data
        meeting_id = data.get('meetingId')
        event_type = data.get('eventType')

        if not meeting_id or event_type != 'Transcription completed':
            return jsonify({'error': 'Invalid data'}), 400

        # Step 3: Fetch transcript details
        transcript_details = fetch_transcript_details(meeting_id, api_key)
        if not transcript_details:
            logging.error("Transcript details not found.")
            return jsonify({'error': 'Transcript details not found'}), 400

        # Extract transcript content and metadata
        content = process_transcript_content(transcript_details)
        speakers = get_transcript_speakers(transcript_details)
        title = transcript_details.get('title', 'Untitled Transcript')

        # Save transcript as PDF
        pdf_file_path = save_transcript_as_pdf(transcript_details, content)
        logging.info(f"Transcript saved as PDF at: {pdf_file_path}")

        # Rule 1 check using GPT analysis
        rule1_passed, analysis = analyze_transcript_with_gpt(content, title)

        if not rule1_passed:
            logging.warning(f"Rule failed for title: {title}")
            return jsonify({'status': 'logged', 'analysis': analysis}), 200

        # Step 4: Retrieve meeting details, notes, and investor report
        result = get_meeting_details_and_notes_by_fuzzy_title(title)
        meeting_details = result.get('meeting_details', {})
        notes = result.get('notes', [])
        investor_report = result.get('investor_report')

        # Step 5: Vectorize data
        vectorize_data(content, "transcripts", meeting_id, title)

        # Process meeting details
        if meeting_details:
            detail_content = f"Title: {meeting_details['title']}\nScheduled Time: {meeting_details['scheduled_time']}\n"
            vectorize_data(detail_content, "meeting_details", meeting_id, title)
            content += "\n\nMeeting Details:\n" + detail_content

        # Process meeting notes
        if notes:
            notes_content = "\n".join(notes)
            vectorize_data(notes_content, "meeting_notes", meeting_id, title)
            content += "\n\nMeeting Notes:\n" + notes_content

        # Process investor report
        report_content = ""
        if investor_report:
            report_content = process_investor_report(investor_report, meeting_id, title)
            vectorize_data(report_content, "investor_report", meeting_id, title)
            content += "\n\nInvestor Report:\n" + report_content

        # Role Identification Step
        roles = role_identifier(content, notes, report_content, meeting_details, speakers)

        # Step 6: Analyze with logic block
        nda_mentioned, nda_gpt_analysis, dataroom_mentioned, dataroom_gpt_analysis, prenda_mentioned, prenda_gpt_analysis = logic_block(content, roles)

        # Step 7: Return response
        return jsonify({
            'status': 'success',
            'Rule analysis': analysis,
            'nda_mentioned': nda_mentioned,
            'gpt_reasoning': nda_gpt_analysis,
            "dataroom_mentioned": dataroom_mentioned,
            "dataroom_gpt_reasoning": dataroom_gpt_analysis,
            "prenda_mentioned": prenda_mentioned,
            "prenda_gpt_reasoning": prenda_gpt_analysis,
            'details': {
                'id': transcript_details.get('id'),
                'title': title,
                'meeting_details': meeting_details,
                'notes': notes,
                'investor_report': investor_report
            },
            "gpt analysis for role identification": roles
        }), 200

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

    finally:
        # Release lock after completion
        request_lock.release()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

