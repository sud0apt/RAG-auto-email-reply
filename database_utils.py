import pymysql
import logging
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)

# Database Configuration
DB_CONFIG = {
    "host": "xxxx",
    "database": "xxxx",
    "user": "xxxx",
    "password": "xxxx",
}


def get_meeting_details_and_notes_by_fuzzy_title(transcript_title):
    """
    Fetches the latest meeting details, investor report, and notes using fuzzy matching for transcript_title.
    Ensures the latest meeting with an investor report is retrieved. Raises an error if no report is found.
    """
    try:
        # Connect to the database
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor()

        # Fetch all meetings with details and investor reports
        cursor.execute("""
            SELECT meeting_id, meeting_title, scheduled_time, investor_report 
            FROM sandbox_db.meetings
            ORDER BY scheduled_time DESC
        """)
        meetings = cursor.fetchall()  # [(id, title, scheduled_time, investor_report), ...]

        # Fuzzy match the title
        best_match = process.extractOne(transcript_title, [m[1] for m in meetings], scorer=fuzz.token_sort_ratio)

        if best_match[1] < 50:  # Require at least 50% similarity
            logging.warning(f"No close match found for title: {transcript_title}")
            raise ValueError(f"No close match found for title: {transcript_title}")

        # Get the latest matched meeting with an investor report
        matched_meetings = [
            m for m in meetings if m[1] == best_match[0] and m[3]  # Investor report must exist
        ]

        if not matched_meetings:
            raise ValueError(f"No meeting with investor report found for title: {transcript_title}")

        # Select the latest meeting
        matched_meeting = matched_meetings[0]
        matched_id = matched_meeting[0]
        meeting_title = matched_meeting[1]
        scheduled_time = matched_meeting[2]
        investor_report = matched_meeting[3]

        logging.info(f"Matched Meeting ID: {matched_id}")
        logging.info(f"Investor report: {investor_report}")

        # Fetch notes for the matched meeting_id
        cursor.execute("""
            SELECT note_text 
            FROM crm_portal.meeting_notes 
            WHERE meeting_id = %s
        """, (matched_id,))
        notes = cursor.fetchall()

        # Close database connection
        cursor.close()
        connection.close()

        return {
            "meeting_details": {
                "id": matched_id,
                "title": meeting_title,
                "scheduled_time": scheduled_time
            },
            "investor_report": investor_report,
            "notes": [note[0] for note in notes] if notes else []
        }

    except Exception as e:
        logging.error(f"Database error: {e}")
        raise e
