import json
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
from openai import OpenAI
import base64
import difflib

# News sources to monitor
SOURCES = [
    {
        'name': 'MDR Sachsen-Anhalt',
        'feed': 'https://www.mdr.de/nachrichten/index-rss.xml',
        'keywords': ['übergriff', 'rassismus', 'magdeburg', 'angriff', 'gewalt']
    },
    {
        'name': 'taz',
        'feed': 'https://taz.de/!p4608;rss/',
        'keywords': ['magdeburg', 'rassismus', 'übergriff', 'angriff', 'gewalt', 'rechtsextrem', 'fremdenfeindlich']
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
    
    # MDR specific extraction
    if 'mdr.de' in url:
        article = soup.select_one('article')
        if article:
            paragraphs = article.select('p')
            return ' '.join(p.get_text() for p in paragraphs)
    
    # taz specific extraction
    if 'taz.de' in url:
        article = soup.select_one('.article')
        if article:
            paragraphs = article.select('p')
            return ' '.join(p.get_text() for p in paragraphs)
    
    return None

def parse_with_llm(article_text, url, source_name):
    """Use OpenAI to parse article text into structured incident data"""
    
    prompt = f"""Extract incident information from this article text. Format as JSON with:
    - date (YYYY-MM-DD)
    - location (specific place in Magdeburg)
    - description (short factual description)
    - sources (array with url and name)
    - type (physical_attack, verbal_attack, property_damage, or other)
    - status (verified if confirmed by police/officials)

    Article text:
    {article_text}
    """

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        incident = json.loads(response.choices[0].message.content)
        incident['sources'].append({
            'url': url,
            'name': source_name
        })
        return incident
    except:
        print(f"Failed to parse incident from {url}")
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

def is_duplicate(new_incident, existing_incidents):
    """Check if an incident is already recorded using GPT-4"""
    # First check exact URL matches
    for existing in existing_incidents:
        existing_urls = {source['url'] for source in existing['sources']}
        new_urls = {source['url'] for source in new_incident['sources']}
        if existing_urls & new_urls:  # If there's any overlap in URLs
            return True

    # For incidents on the same date, use GPT-4 to check if they're the same
    same_date_incidents = [
        incident for incident in existing_incidents 
        if incident['date'] == new_incident['date']
    ]
    
    if same_date_incidents:
        prompt = f"""Compare these incidents and determine if they are the same event reported differently.
        Consider location, type of attack, and description details.
        Return only "true" if they are the same incident, or "false" if different.

        Incident 1:
        Location: {new_incident['location']}
        Description: {new_incident['description']}
        Type: {new_incident['type']}

        Compare with each:
        {json.dumps([{
            'location': inc['location'],
            'description': inc['description'],
            'type': inc['type']
        } for inc in same_date_incidents], indent=2, ensure_ascii=False)}
        """

        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[{
                "role": "user", 
                "content": prompt
            }],
            temperature=0
        )

        is_same = response.choices[0].message.content.strip().lower() == "true"
        
        if is_same:
            # Merge sources if it's the same incident
            for existing in same_date_incidents:
                existing_urls = {source['url'] for source in existing['sources']}
                existing['sources'].extend([
                    s for s in new_incident['sources'] 
                    if s['url'] not in existing_urls
                ])
            return True

    return False

def main():
    current_data = load_current_incidents()
    new_incidents = []
    
    for source in SOURCES:
        feed = feedparser.parse(source['feed'])
        
        for entry in feed.entries:
            if any(keyword in entry.title.lower() or 
                  keyword in entry.description.lower() 
                  for keyword in source['keywords']):
                
                article_text = extract_text_from_article(entry.link)
                if not article_text:
                    continue
                
                incident = parse_with_llm(article_text, entry.link, source['name'])
                if incident and not is_duplicate(incident, current_data['incidents']):
                    new_incidents.append(incident)
    
    if new_incidents:
        current_data['incidents'].extend(new_incidents)
        current_data['lastUpdated'] = datetime.utcnow().isoformat() + 'Z'
        create_pull_request(current_data)

if __name__ == '__main__':
    main() 