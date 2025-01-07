import json
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
from openai import OpenAI
import base64

# News sources to monitor
SOURCES = [
    {
        'name': 'MDR Sachsen-Anhalt',
        'feed': 'https://www.mdr.de/nachrichten/index-rss.xml',
        'keywords': ['übergriff', 'rassismus', 'magdeburg', 'angriff', 'gewalt']
    }
]

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def load_current_incidents():
    with open('data/incidents.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_text_from_article(url):
    """Extract main article text from URL"""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # MDR specific extraction - adjust selectors as needed
    article = soup.select_one('article')
    if not article:
        return None
    
    paragraphs = article.select('p')
    return ' '.join(p.get_text() for p in paragraphs)

def parse_with_llm(article_text, url, source_name):
    """Use OpenAI to parse article text into structured incident data"""
    
    prompt = f"""
    Analyze this news article about potential hate crimes or racist incidents in Magdeburg and extract the following information in JSON format:
    - Date and time of the incident (if mentioned)
    - Location (district and city)
    - Description of what happened
    - Whether this appears to be a verified incident
    
    Only return incidents that are clearly hate crimes or racist attacks. If no such incident is described, return null.
    
    Format the response as a JSON object matching this structure:
    {{
        "date": "YYYY-MM-DDTHH:MM:SS+01:00",
        "location": {{
            "city": "Magdeburg",
            "district": "district name",
            "coordinates": null
        }},
        "description": "Description in German",
        "sources": [
            {{
                "name": "{source_name}",
                "url": "{url}",
                "date": "YYYY-MM-DD"
            }}
        ],
        "officialReportId": null,
        "verificationStatus": "verified"
    }}

    Article text:
    {article_text}
    """

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": "You are a precise incident data extractor. Only extract verified incidents of hate crimes or racist attacks in Magdeburg. Return null if no such incident is described."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    try:
        result = json.loads(response.choices[0].message.content)
        if result and result.get('date'):  # Only return if incident was found
            # Generate an ID based on the date
            date_part = result['date'][:10].replace('-', '')
            result['id'] = f"{date_part}-001"  # You might want to handle multiple incidents per day
            return result
        return None
    except json.JSONDecodeError:
        return None

def create_pull_request(new_incidents):
    """Create a PR with new incidents"""
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    
    if not repo or not token:
        print("Missing repository information or token")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    api_base = "https://api.github.com"

    # Create a new branch
    branch_name = f"update-incidents-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # Get the current main branch SHA
    r = requests.get(f"{api_base}/repos/{repo}/git/ref/heads/main", headers=headers)
    if r.status_code != 200:
        print("Failed to get main branch reference")
        return
    main_sha = r.json()["object"]["sha"]

    # Create new branch
    data = {
        "ref": f"refs/heads/{branch_name}",
        "sha": main_sha
    }
    r = requests.post(f"{api_base}/repos/{repo}/git/refs", headers=headers, json=data)
    if r.status_code != 201:
        print("Failed to create branch")
        return

    # Update file in new branch
    with open('data/incidents.json', 'r', encoding='utf-8') as f:
        content = f.read()
    
    data = {
        "message": f"Add {len(new_incidents)} new incidents",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch_name
    }
    
    r = requests.put(
        f"{api_base}/repos/{repo}/contents/data/incidents.json",
        headers=headers,
        json=data
    )
    
    if r.status_code != 200:
        print("Failed to update file")
        return

    # Create PR
    pr_data = {
        "title": f"Add {len(new_incidents)} new incidents",
        "body": "Automatically detected new incidents from news sources.",
        "head": branch_name,
        "base": "main"
    }
    
    r = requests.post(f"{api_base}/repos/{repo}/pulls", headers=headers, json=pr_data)
    if r.status_code != 201:
        print("Failed to create PR")
        return
    
    print(f"Created PR: {r.json()['html_url']}")

def main():
    current_data = load_current_incidents()
    existing_urls = {source['url'] for incident in current_data['incidents'] 
                    for source in incident['sources']}
    
    new_incidents = []
    
    for source in SOURCES:
        feed = feedparser.parse(source['feed'])
        
        for entry in feed.entries:
            if any(keyword in entry.title.lower() or 
                  keyword in entry.description.lower() 
                  for keyword in source['keywords']):
                
                if entry.link in existing_urls:
                    continue
                
                article_text = extract_text_from_article(entry.link)
                if not article_text:
                    continue
                
                incident = parse_with_llm(article_text, entry.link, source['name'])
                if incident:
                    new_incidents.append(incident)
    
    if new_incidents:
        current_data['incidents'].extend(new_incidents)
        current_data['lastUpdated'] = datetime.utcnow().isoformat() + 'Z'
        create_pull_request(current_data)

if __name__ == '__main__':
    main() 