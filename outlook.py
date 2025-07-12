import requests
import json

# Azure AD and API details
TENANT_ID = 'xxxx'
CLIENT_ID = 'xxxx'
CLIENT_SECRET = 'xxxx'
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPES = ['https://graph.microsoft.com/.default']
USER_EMAIL = 'xxxx'  
EMAIL_API_URL = f'https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/sendMail'

# Function to get access token
def get_access_token_outlook():
    url = f'{AUTHORITY}/oauth2/v2.0/token'
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': ' '.join(SCOPES)
    }
    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json().get('access_token')

# Function to send email
def send_email(access_token, recipient_email, subject, body):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    email_data = {
        'message': {
            'subject': subject,
            'body': {
                'contentType': 'HTML',
                'content': body
            },
            'toRecipients': [
                {
                    'emailAddress': {'address': recipient_email}
                }
            ]
        }
    }
    response = requests.post(EMAIL_API_URL, headers=headers, data=json.dumps(email_data))
    if response.status_code == 202:
        print('Email sent successfully!')
    else:
        print(f'Error sending email: {response.status_code} - {response.text}')

if __name__ == '__main__':
    try:
        recipient_email = 'xxxx'
        subject = 'Test Email from Python Script'
        body = '<h1>Hello!</h1><p>This is a test email sent using Outlook API.</p>'
        
        token = get_access_token_outlook()
        
        send_email(token, recipient_email, subject, body)
    except Exception as e:
        print(f'Error: {e}')
