import openai
import logging
import re  # For parsing speaker roles
import json  # For JSON parsing
from transcript_utils import *
import re
from transcript_utils import get_transcript_speakers

# OpenAI API Key
OPENAI_API_KEY = 'xxxx'
openai.api_key = OPENAI_API_KEY

def classify_context(selected_flow, retrieved_context, roles):
    """
    Classify retrieved context into one of the scenarios based on the selected flow.
    Returns the exact matching scenario text along with the category name, reason, and quote.
    """
    # Define GPT prompt for classification
    prompt = f"""
    Classify the following retrieved context into scenarios based on the selected flow: {selected_flow.value}

    Scenarios:
    NDA:
        - Investor asks for NDA
        - Lead/Client says they will send NDA or wait for NDA

    Data Room:
        - Investor requests data room
        - Client/lead says send data room

    Pre-NDA:
        - Investor requests additional/supporting docs
        - Client/lad says they will send additional docs

    Rules:
    1. Return the **exact matching scenario text** followed by the **category name** (e.g., 'Investor asks for NDA and NDA').
    2. Provide a **reason** explaining why this classification was chosen using references to {roles}.
    3. Include a **direct quote** from the retrieved context that supports the classification.
    4. If no match is found, return 'None'.

    Context:
    \"\"\"{retrieved_context}\"\"\"
    \"\"\"{roles}\"\"\"

    Output format:
    {{
        "scenario": "<scenario text> and <category>",
        "reason": "<reason for classification>",
        "quote": "<direct quote from context>"
    }}
    """

    try:
        # Make GPT-4 call
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an AI assistant designed to classify into fixed scenarios and provide reasons with quotes."},
                {"role": "user", "content": prompt}
            ]
        )

        # Extract and log classification
        classification = response.choices[0].message.content.strip()
        logging.info(f"Classification: {classification}")

        # Return classification result directly
        return classification

    except Exception as e:
        logging.error(f"Error in classify_context: {e}")
        return {
            "scenario": "None",
            "reason": "Error occurred during classification.",
            "quote": ""
        }


def role_identifier(transcript, notes, investor_report, meeting_details,speakers):
    """
    Identifies roles of speakers based on transcript, notes, investor report, and meeting details.
    Roles: 'Facilitator', 'Investor', 'Client'.
    """

    # GPT Prompt for Role Classification
    prompt = f"""
    Classify the role of the {speakers} based on investor report. If name in investor report, classify as 'Investor'. If not, use predefined names to identify 'Facilitator'. If no match, assign 'Client'.

    Roles:
    - Facilitator: Guides discussions, organizes meetings, moderates topics. Known facilitators: Santiago, Kyle, Jackie.
    - Investor: Focuses on investments, funding, or capital allocation. Often linked to investor reports.
    - Client: Discusses business needs, services, or products, particularly seeking funding or partnerships. 
    - Guest: Default if no clear role applies.

    Investor Report:
    {investor_report}

    Output format (only output the json do not output any other text):
    {{
        "speaker": <Speaker>,
        "role": "<Role>",
        "reason": "<Reason>"
    }}
    """

    # Call GPT-4 API
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Filter speakers then classify speaker roles based on context."},
            {"role": "user", "content": prompt}
        ]
    )

    # Process GPT response
    gpt_reply = response.choices[0].message.content.strip()
    logging.info(f"GPT Analysis: {gpt_reply}")

    return gpt_reply
