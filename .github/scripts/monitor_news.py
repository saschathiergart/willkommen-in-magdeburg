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
        'keywords': [
            'magdeburg', 
            'rassistisch', 
            'fremdenfeindlich',
            'ausländerfeindlich',
            'hassverbrechen',
            'übergriff',
            'angriff migranten',
            'rassismus'
        ]
    },
    {
        'name': 'taz',
        'feed': 'https://taz.de/!p4608;rss/',
        'keywords': [
            'magdeburg',
            'rassistisch',
            'fremdenfeindlich',
            'ausländerfeindlich',
            'hassverbrechen',
            'übergriff',
            'angriff migranten',
            'rassismus'
        ]
    },
    {
        'name': 'sz',
        'feed': 'https://rss.sueddeutsche.de/alles',
        'keywords': [
            'magdeburg',
            'rassistisch',
            'fremdenfeindlich',
            'ausländerfeindlich',
            'hassverbrechen',
            'übergriff',
            'angriff migranten',
            'rassismus'
        ]
    },
    {
        'name': 'Mobile Opferberatung',
        'feed': 'https://www.mobile-opferberatung.de/monitoring/chronik-2024',
        'keywords': [
            'magdeburg',
            'rassistisch',
            'fremdenfeindlich',
            'ausländerfeindlich',
            'hassverbrechen',
            'übergriff',
            'angriff migranten',
            'rassismus'
        ]
    },
    {
        'name': 'Landesportal Sachsen-Anhalt - Pressemitteilungen der Polizei',
        'feed': 'https://www.sachsen-anhalt.de/bs/pressemitteilungen/rss-feeds?tx_tsarssinclude_rss%5Baction%5D=feed&tx_tsarssinclude_rss%5Bcontroller%5D=Rss&tx_tsarssinclude_rss%5Buid%5D=75&type=9988&cHash=6052a14b7487702c9e9ca69eac34418a',
        'keywords': [
            'magdeburg',
            'rassistisch',
            'fremdenfeindlich',
            'ausländerfeindlich',
            'hassverbrechen',
            'übergriff',
            'angriff migranten',
            'rassismus'
        ]
    }
]

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def load_current_incidents():
    with open('data/incidents.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_text_from_article(url):
    """Extract main article text from URL"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'de,en-US;q=0.7,en;q=0.3'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # MDR specific extraction
        if 'mdr.de' in url:
            # Try different possible article containers
            article = (
                soup.select_one('.content article') or 
                soup.select_one('main article') or
                soup.select_one('.mdr-page__content')
            )
            
            if article:
                # Get text from paragraphs and headlines
                text_elements = article.select('p, h1, h2, h3')
                return ' '.join(elem.get_text(strip=True) for elem in text_elements)
        
        # taz specific extraction
        if 'taz.de' in url:
            article = soup.select_one('article.article')
            if article:
                text_elements = article.select('p:not(.article__meta), h1, h2')
                return ' '.join(elem.get_text(strip=True) for elem in text_elements)
        
        print(f"Could not find article content in {url}")
        return None
        
    except Exception as e:
        print(f"Error extracting text from {url}: {str(e)}")
        return None

def parse_with_llm(article_text, url, source_name):
    """Use OpenAI to parse article text into structured incident data"""
    
    prompt = f"""Analysiere diesen Artikel streng nach folgenden Kriterien für rassistisch motivierte Vorfälle in Magdeburg.

    Ein Vorfall muss ALLE diese Kriterien erfüllen:
    1. Der Vorfall fand definitiv in Magdeburg statt
    2. Es handelt sich eindeutig um einen rassistisch oder fremdenfeindlich motivierten Übergriff
    3. Der Vorfall geschah nach dem 20. Dezember 2024
    4. Der Vorfall ist durch offizielle Quellen (Polizei, Behörden) oder mehrere unabhängige Zeugen bestätigt
    5. Es gibt eine klare rassistische oder fremdenfeindliche Motivation (z.B. durch Äußerungen oder Kontext)

    Antworte mit "null" wenn:
    - Auch nur EINES der obigen Kriterien nicht eindeutig erfüllt ist
    - Der Artikel nur allgemein über Rassismus berichtet
    - Der Artikel sich auf frühere Vorfälle bezieht
    - Es Zweifel an der rassistischen Motivation gibt
    - Der Vorfall nicht in Magdeburg stattfand
    - Der Vorfall nicht ausreichend verifiziert ist

    Falls ALLE Kriterien erfüllt sind, formatiere den Vorfall als JSON mit:
    - date (YYYY-MM-DD)
    - location (präziser Ort in Magdeburg)
    - description (kurze faktische Beschreibung mit Nennung der Quelle der Verifizierung)
    - sources (Array mit url und name)
    - type (physical_attack, verbal_attack, property_damage, oder other)
    - status (verified wenn von Polizei/Behörden bestätigt)

    Artikel:
    {article_text}
    """

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[{
            "role": "system",
            "content": "Du bist ein sehr kritischer Fact-Checker. Gib nur Vorfälle zurück, die zu 100% verifiziert und relevant sind."
        }, {
            "role": "user",
            "content": prompt
        }],
        temperature=0
    )

    try:
        result = response.choices[0].message.content.strip()
        if result.lower() == "null":
            return None
            
        incident = json.loads(result)
        # Add source if not already included
        if not any(s['url'] == url for s in incident.get('sources', [])):
            incident.setdefault('sources', []).append({
                'url': url,
                'name': source_name
            })
        return incident
    except Exception as e:
        print(f"Failed to parse incident from {url}: {str(e)}")
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

def debug_feed(feed_url):
    """Debug RSS feed access"""
    print(f"\nTesting feed: {feed_url}")
    try:
        response = requests.get(
            feed_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/rss+xml, application/xml'
            },
            allow_redirects=False  # Don't follow redirects to see what's happening
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 301 or response.status_code == 302:
            print(f"Redirects to: {response.headers.get('Location')}")
        return response.status_code
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def main():
    print("\n=== News Monitor Starting ===")
    print(f"Time: {datetime.now().isoformat()}")
    
    # Check OpenAI API key first
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        return
    if not api_key.startswith("sk-"):
        print("Error: Invalid OpenAI API key format")
        return
        
    current_data = load_current_incidents()
    new_incidents = []
    articles_checked = 0
    keywords_matched = 0
    
    print("\nCurrent incidents in database:", len(current_data['incidents']))
    
    for source in SOURCES:
        print(f"\nProcessing feed: {source['feed']}")
        try:
            response = requests.get(source['feed'])
            response.encoding = 'utf-8'
            feed = feedparser.parse(response.text)
            
            if feed.bozo:
                print(f"Error parsing feed: {feed.bozo_exception}")
                continue
                
            print(f"Found {len(feed.entries)} entries")
            
            for entry in feed.entries:
                articles_checked += 1
                if any(keyword in entry.title.lower() or 
                      keyword in getattr(entry, 'description', '').lower()
                      for keyword in source['keywords']):
                    
                    keywords_matched += 1
                    print(f"\nPotential incident found in: {entry.title}")
                    print(f"URL: {entry.link}")
                    
                    article_text = extract_text_from_article(entry.link)
                    if not article_text:
                        continue
                    
                    try:
                        incident = parse_with_llm(article_text, entry.link, source['name'])
                        if incident and not is_duplicate(incident, current_data['incidents']):
                            print("✓ New verified incident found!")
                            print(f"Location: {incident['location']}")
                            print(f"Date: {incident['date']}")
                            print(f"Type: {incident['type']}")
                            new_incidents.append(incident)
                    except Exception as e:
                        print(f"Error processing article: {str(e)}")
                        continue
                        
        except Exception as e:
            print(f"Error processing feed: {str(e)}")
            continue
    
    print("\n=== News Monitor Summary ===")
    print(f"Articles checked: {articles_checked}")
    print(f"Keyword matches: {keywords_matched}")
    print(f"New incidents found: {len(new_incidents)}")
    
    if new_incidents:
        current_data['incidents'].extend(new_incidents)
        current_data['lastUpdated'] = datetime.utcnow().isoformat() + 'Z'
        create_pull_request(current_data)
        print("\nCreated pull request with new incidents")
    else:
        print("\nNo new incidents to add")
    
    print("==========================")

if __name__ == '__main__':
    main() 
