"""
ASTM Material Extraction Agent (Gemini + Tavily)
=================================================
Run this locally where you have API access.

Requirements:
    pip install google-generativeai tavily-python pandas openpyxl

Usage:
    python astm_extractor_local.py
"""

import os
import json
import time
import re
from typing import List
import pandas as pd
import google.generativeai as genai
from tavily import TavilyClient

# --- API KEYS ---
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- STANDARDS TO PROCESS ---
# Start with 5 for testing, add more as needed
STANDARDS_TO_PROCESS = [
    "A106",   # Seamless Carbon Steel Pipe
    "A312",   # Austenitic Stainless Steel Pipe  
    "A182",   # Forged Alloy/Stainless Steel
    "A333",   # Low-Temperature Pipe
    "A234",   # Wrought Carbon/Alloy Fittings
    # Uncomment to add more:
    # "A53",    # Welded/Seamless Pipe
    # "A105",   # Carbon Steel Forgings
    # "A335",   # Seamless Ferritic Alloy Pipe
    # "A403",   # Wrought Austenitic SS Fittings
    # "A420",   # Low-Temp Fittings
    # "A516",   # Pressure Vessel Plate
]

OUTPUT_FILE = "astm_grades_database.xlsx"

# --- INITIALIZE CLIENTS ---
print("Initializing API clients...")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')
tavily = TavilyClient(api_key=TAVILY_API_KEY)


def search_tavily(query: str, max_results: int = 5) -> str:
    """Search Tavily and return combined context"""
    print(f"  [Tavily] Searching: '{query[:50]}...'")
    try:
        response = tavily.search(
            query=query,
            search_depth="advanced",
            max_results=max_results
        )
        
        context = ""
        for result in response.get("results", []):
            context += f"Source: {result['url']}\n"
            context += f"{result['content']}\n\n"
        
        return context[:15000]
    except Exception as e:
        print(f"  [Error] Tavily search failed: {e}")
        return ""


def extract_json_from_response(text: str) -> list:
    """Extract JSON array from Gemini response"""
    # Try to find JSON in code blocks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        text = json_match.group(1)
    
    text = text.strip()
    
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and 'grades' in result:
            return result['grades']
        return [result]
    except json.JSONDecodeError:
        start = text.find('[')
        if start != -1:
            try:
                return json.loads(text[start:])
            except:
                pass
    return []


def process_standard(standard_id: str) -> list:
    """Process a single ASTM standard"""
    print(f"\n{'='*60}")
    print(f"PROCESSING: ASTM {standard_id}")
    print('='*60)
    
    # Search for grade information
    query = f"ASTM {standard_id} all grades types material specifications UNS chemical composition"
    context = search_tavily(query)
    
    if not context:
        print(f"  [Warning] No search results for {standard_id}")
        return []
    
    # Extract with Gemini
    prompt = f"""You are a metallurgical data specialist. Extract ALL material grades from ASTM {standard_id}.

Context from web search:
{context}

For each grade, extract:
1. astm_standard: "{standard_id}"
2. grade: Grade designation (e.g., "B", "TP304", "WPB", "F11")
3. material_type: Full name (e.g., "Carbon Steel", "Stainless Steel", "Chrome-Moly Steel")
4. abbreviation: Short code (CS, SS, CrMo, ALY, LTCS)
5. uns_number: UNS if known (e.g., "K03006", "S30400"), or null
6. composition: Alloy formula (e.g., "1.25Cr-0.5Mo", "18Cr-8Ni"), or null
7. manufacturing_type: "Seamless", "Forged", "Wrought", "Cast", or "Welded"
8. description: Brief 1-line description

Return ONLY a JSON array. Example:
[
  {{"astm_standard": "A106", "grade": "B", "material_type": "Carbon Steel", "abbreviation": "CS", "uns_number": "K03006", "composition": null, "manufacturing_type": "Seamless", "description": "Standard carbon steel pipe for high-temp service"}}
]

Extract ALL grades. Return ONLY valid JSON array:"""

    print(f"  [Gemini] Extracting grades...")
    
    try:
        response = model.generate_content(prompt)
        records = extract_json_from_response(response.text)
        
        if records:
            print(f"  [OK] Extracted {len(records)} grades")
            for r in records:
                print(f"       - {r.get('grade', '?')}: {r.get('material_type', '?')}")
            return records
        else:
            print(f"  [Warning] No grades extracted")
            return []
            
    except Exception as e:
        print(f"  [Error] Gemini API error: {e}")
        return []


def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("ASTM MATERIAL EXTRACTION AGENT")
    print("Stack: Gemini 2.0 Flash + Tavily Search")
    print("="*70)
    print(f"\nProcessing {len(STANDARDS_TO_PROCESS)} standards: {STANDARDS_TO_PROCESS}")
    
    all_records = []
    
    for standard in STANDARDS_TO_PROCESS:
        try:
            records = process_standard(standard)
            all_records.extend(records)
            print(f"\n  >>> Total records: {len(all_records)}")
        except Exception as e:
            print(f"\n  [ERROR] Failed to process {standard}: {e}")
        
        time.sleep(2)  # Rate limiting
    
    if not all_records:
        print("\n[ERROR] No records extracted!")
        return None
    
    # Create DataFrame
    df = pd.DataFrame(all_records)
    
    # Ensure columns exist
    expected_columns = [
        'astm_standard', 'grade', 'material_type', 'abbreviation',
        'uns_number', 'composition', 'manufacturing_type', 'description'
    ]
    
    for col in expected_columns:
        if col not in df.columns:
            df[col] = None
    
    # Add combined name
    df.insert(2, 'combined_name', df['astm_standard'] + ' - ' + df['grade'].astype(str))
    
    # Reorder
    columns = ['astm_standard', 'grade', 'combined_name', 'material_type', 'abbreviation',
               'uns_number', 'composition', 'manufacturing_type', 'description']
    df = df[[c for c in columns if c in df.columns]]
    
    # Save to Excel
    df.to_excel(OUTPUT_FILE, index=False, sheet_name="ASTM_Grades")
    
    print("\n" + "="*70)
    print("EXTRACTION COMPLETE")
    print("="*70)
    print(f"Total grades: {len(df)}")
    print(f"Output file: {OUTPUT_FILE}")
    print("\nBreakdown:")
    print(df.groupby('astm_standard').size())
    print("\nPreview:")
    print(df.head(20).to_string())
    
    return df


if __name__ == "__main__":
    df = main()
