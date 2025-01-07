from monitor_news import extract_text_from_article, parse_with_llm
import json

# Test URL - the MDR article about the incidents
TEST_URL = "https://www.mdr.de/nachrichten/sachsen-anhalt/magdeburg/magdeburg/attentat-weihnachtsmarkt-neue-details-gewaltsame-angriffe-migranten-112.html"

def test_parser():
    # Extract article text
    print("Extracting article text...")
    article_text = extract_text_from_article(TEST_URL)
    if not article_text:
        print("Failed to extract article text")
        return
    
    print("\nExtracted text:")
    print(article_text[:500] + "...")  # Print first 500 chars
    
    # Parse with LLM
    print("\nParsing with LLM...")
    incident = parse_with_llm(article_text, TEST_URL, "MDR")
    
    if incident:
        print("\nExtracted incident:")
        print(json.dumps(incident, indent=2, ensure_ascii=False))
    else:
        print("\nNo incident extracted")

if __name__ == "__main__":
    test_parser() 