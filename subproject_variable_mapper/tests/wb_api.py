"""
WB API module with LangGraph, OpenAI, and Anthropic integrations.
This module provides functionality for working with the World Bank API
along with AI agent capabilities using LangGraph, OpenAI, and Anthropic models.
"""

import os
import time
import requests
import re
from datetime import datetime
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.graph import Graph
import openai
from anthropic import Anthropic
from playwright.sync_api import sync_playwright
import pandas as pd
from pprint import pprint

# Load environment variables from .env file
load_dotenv()

# Initialize API clients
openai_client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

anthropic_client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

class WbState:
    """
    State class that will be propagated between nodes in the WB workflow.
    """
    def __init__(self):
        self.user_query = ""  # User's original query
        self.search_keyword = []  # List of strings for search keywords
        self.search_result = {}  # Dict to store keyword: DataFrame pairs
        self.selected_api = {}  # Dict to store endpoint: [limitation, reasoning] pairs
        self.collected_data = {}  # Dict to store keyword: DataFrame pairs from API calls
        self.unavailable_data = {}  # Dict to store data_point: reason pairs

def search_node(state: WbState):
    """Search node that queries World Bank API for each keyword"""
    
    for keyword in state.search_keyword:
        print(f"Searching for: {keyword}")
        
        # World Bank API endpoint
        url = "https://data360api.worldbank.org/data360/searchv2"
        
        # Request payload
        payload = {
            "count": True,
            "select": "series_description/idno, series_description/name, series_description/database_id",
            "search": keyword,
            "top": 5
        }
        
        # Headers
        headers = {
            'accept': '*/*',
            'Content-Type': 'application/json'
        }
        
        try:
            # Make POST request
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            print(f"API Response for '{keyword}':")
            pprint(data)
            
            # Transform response into DataFrame
            if 'value' in data and data['value']:
                df_data = []
                for item in data['value']:
                    series_desc = item.get('series_description', {})
                    df_data.append({
                        'db_id': series_desc.get('database_id', ''),
                        'idno': series_desc.get('idno', ''),
                        'name': series_desc.get('name', ''),
                        'search_score': item.get('@search.score', 0)
                    })
                
                df = pd.DataFrame(df_data)
                print(f"✅ Search results for '{keyword}': {len(df)} APIs found")
                
                # Fetch metadata for each IDNO and add to DataFrame
                print(f"\nFetching metadata for each IDNO in '{keyword}'...")
                
                # Initialize metadata columns
                metadata_columns = ['definition_long', 'statistical_concept', 'limitation', 
                                  'relevance', 'aggregation_method', 'time_periods']
                for col in metadata_columns:
                    df[col] = ''
                
                for idx, row in df.iterrows():
                    idno = row['idno']
                    print(f"\n--- Fetching metadata for IDNO: {idno} ---")
                    metadata = fetch_metadata_for_idno(idno)
                    
                    if metadata and 'value' in metadata and metadata['value']:
                        series_desc = metadata['value'][0].get('series_description', {})
                        
                        # Extract metadata fields and add to DataFrame
                        df.at[idx, 'definition_long'] = series_desc.get('definition_long', '')
                        df.at[idx, 'statistical_concept'] = series_desc.get('statistical_concept', '')
                        df.at[idx, 'limitation'] = series_desc.get('limitation', '')
                        df.at[idx, 'relevance'] = series_desc.get('relevance', '')
                        df.at[idx, 'aggregation_method'] = series_desc.get('aggregation_method', '')
                        df.at[idx, 'time_periods'] = str(series_desc.get('time_periods', ''))
                        
                        print(f"Metadata added for {idno}")
                    else:
                        print(f"No metadata found for {idno}")
                    
                    # Add slight pause between metadata calls to handle rate limits
                    time.sleep(0.5)
                
                # Store DataFrame in search_result
                state.search_result[keyword] = df
                print(f"✅ Metadata added for '{keyword}': {len(df)} APIs with full metadata")
            else:
                print(f"No 'value' data found in response for '{keyword}'")
                state.search_result[keyword] = pd.DataFrame()
            
        except requests.exceptions.RequestException as e:
            print(f"Error making API request for '{keyword}': {e}")
        except Exception as e:
            print(f"Unexpected error for '{keyword}': {e}")
        
        # Add 1 second delay between requests
        time.sleep(1)
    
    return state

def fetch_metadata_for_idno(idno):
    """Fetch metadata for a specific IDNO from World Bank API"""
    url = "https://data360api.worldbank.org/data360/metadata"
    
    # Request payload
    payload = {
        "query": f"&$filter=series_description/idno eq '{idno}'&$select=series_description/definition_long,series_description/statistical_concept,series_description/limitation,series_description/relevance,series_description/aggregation_method,series_description/time_periods"
    }
    
    # Headers
    headers = {
        'accept': '*/*',
        'Content-Type': 'application/json'
    }
    
    try:
        # Make POST request
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching metadata for '{idno}': {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching metadata for '{idno}': {e}")
        return None

def api_selector_node(state: WbState):
    """API selector node that selects the first row from each keyword's search results"""
    import json
    
    # Step 1: Merge all searched APIs from all keywords into one DataFrame
    all_search_results = []
    for keyword, df in state.search_result.items():
        if not df.empty:
            # Limit to top 10 rows for each keyword
            df_limited = df.head(10)
            # Add keyword column to identify which keyword this result came from
            df_with_keyword = df_limited.copy()
            df_with_keyword['source_keyword'] = keyword
            all_search_results.append(df_with_keyword)
    
    if all_search_results:
        merged_df = pd.concat(all_search_results, ignore_index=True)
        
        # Step 2: Remove duplicated rows (based on db_id and idno columns)
        if 'db_id' in merged_df.columns and 'idno' in merged_df.columns:
            deduplicated_df = merged_df.drop_duplicates(subset=['db_id', 'idno'], keep='first')
        else:
            deduplicated_df = merged_df.drop_duplicates(keep='first')
        
        # Step 2.5: Remove 'relevance' and 'limitation' columns before JSON creation
        columns_to_remove = ['relevance', 'limitation']
        for col in columns_to_remove:
            if col in deduplicated_df.columns:
                deduplicated_df = deduplicated_df.drop(columns=[col])
        
        # Step 3: Print summary
        print(f"\n✅ Merged and deduplicated WB search results: {deduplicated_df.shape[0]} unique APIs")
        
        # Step 5: Call OpenAI LLM to analyze and select APIs
        print("\n" + "="*60)
        print("OPENAI LLM API SELECTION ANALYSIS:")
        print("="*60)
        
        try:
            # Prepare the prompt with user query and JSON data
            prompt = f"""
<role>
You are an API selection specialist for economic data retrieval. Your task is to analyze user requests and select the most relevant APIs from a provided set, prioritizing exact matches for critical data characteristics over broader timeframe coverage.
</role>

<priority_hierarchy>
<priority_1_critical>
**Data Content Match** (Highest Priority)
- Exact indicator/metric requested (e.g., "wages" vs "wage index")
- Correct units (USD vs index vs percentage)
- Proper data type (levels vs rates vs ratios)
- Geographic precision (national vs state vs metro)
</priority_1_critical>

<priority_2_high>
**Data Characteristics**
- Seasonally adjusted vs non-seasonally adjusted (when specified)
- Real vs nominal values (when currency involved)
- Data source authority/reliability
- Current vs historical revisions
</priority_2_high>

<priority_3_medium>
**Frequency and Timeliness**
- Requested data frequency (daily/monthly/quarterly/annual)
- Update frequency and lag
- Data freshness
</priority_3_medium>

<priority_4_lower>
**Timeframe Coverage**
- Coverage of requested time period
- Historical depth
- Data gaps and completeness
</priority_4_lower>
</priority_hierarchy>

<selection_criteria>
<exact_match_principle>
**CRITICAL**: Always prioritize APIs that provide the exact data point requested, even if timeframe coverage is incomplete, over APIs that provide related/proxy indicators with better timeframe coverage.

Examples:
- "Wage Data in USD 2003-2005" > "Wage Index 2000-2005" (even with shorter timeframe)
- "CPI levels" > "CPI growth rates" (even if growth rates have longer history)
- "State unemployment rates" > "National unemployment rate" (even if national has more history)
</exact_match_principle>

<scoring_logic>
Calculate relevance score as:
- Data Content Match: 50% weight
- Data Characteristics: 25% weight  
- Frequency/Timeliness: 15% weight
- Timeframe Coverage: 10% weight
</scoring_logic>
</selection_criteria>

<instructions>
1. **Parse user request** to identify in priority order:
   - Exact data point/indicator needed (MOST CRITICAL)
   - Required units and data type
   - Geographic scope requirements
   - Specific time periods mentioned
   - Required data frequency
   - Any data characteristics (seasonal adjustment, real vs nominal)

2. **Score each API** using priority hierarchy:
   - First assess: Does this provide the EXACT data requested?
   - Then assess: Correct units, geographic scope, data type?
   - Then assess: Appropriate frequency and characteristics?
   - Finally assess: Adequate timeframe coverage?

3. **Rank APIs** with perfect data matches at top, regardless of timeframe limitations

4. **Apply tiebreakers** only among APIs with identical data content:
   - Better timeframe coverage
   - Higher data quality
   - More timely updates
   - Fewer data gaps

5. **Flag timeframe gaps** but don't demote perfect data matches
</instructions>

<examples>
<example>
<user_request>Show me average hourly earnings in US dollars from 2000 to 2010</user_request>
<candidate_apis>
API A: "Average Hourly Earnings, USD" (2005-2010, monthly)
API B: "Employment Cost Index" (2000-2010, quarterly) 
API C: "Real Hourly Earnings, 1982 dollars" (2000-2010, monthly)
</candidate_apis>
<selection_priority>
1. API A (exact match: hourly earnings in USD) - SELECTED despite shorter timeframe
2. API C (close: hourly earnings but wrong units)
3. API B (related but different indicator)
</selection_priority>
</example>
</examples>

<output_format>
Return a JSON object with two arrays:
{{
  "selected_apis": [
    {{
      "endpoint": "API identifier/name",
      "limitation": "specific gaps or limitations relative to user request",
      "reasoning": "explanation of why this API was selected and how it fulfills user requirements"
    }}
  ],
  "unavailable_data": [
    {{
      "data_type": "description of what data is missing",
      "reason": "explanation of why this data is not available in the provided APIs"
    }}
  ]
}}
</output_format>

<selection_guidelines>
- **Data content is king**: Perfect data match with 50% timeframe coverage beats proxy data with 100% coverage
- **Units matter critically**: USD vs index vs percentage are fundamentally different
- **Geographic precision**: State-level request needs state-level data, not national
- **Indicator specificity**: "Wages" ≠ "Employment Cost Index" ≠ "Wage Growth Rate"
- **Flag but don't penalize timeframe gaps**: Note coverage limitations but prioritize data accuracy
- **Multiple perfect matches**: When multiple APIs provide identical data content, then use timeframe as tiebreaker
- **Explain trade-offs**: Always explain why exact data match was prioritized over timeframe coverage
- **Select multiple relevant APIs**: Include all APIs that meaningfully contribute to fulfilling the user request
</selection_guidelines>

<quality_assurance>
Before finalizing selection, verify:
1. ✅ Selected APIs provide the exact data point requested
2. ✅ Units match user requirements  
3. ✅ Geographic scope is appropriate
4. ✅ Any timeframe limitations are clearly flagged in "limitation" field
5. ✅ Reasoning explains priority of data accuracy over coverage
</quality_assurance>

**User Request:** {state.user_query}

**Available APIs (JSON):**
{json_str}

Please analyze the above APIs and select the most relevant ones based on the user request. Return your response as a JSON object following the output format specified above.
"""

            # Call OpenAI LLM
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            llm_response = response.choices[0].message.content
            print("OpenAI LLM Response:")
            print(llm_response)
            
            # Clean the response by removing markdown code blocks
            cleaned_response = llm_response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]  # Remove ```json
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]   # Remove ```
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]  # Remove trailing ```
            cleaned_response = cleaned_response.strip()
            
            # Parse the JSON response
            try:
                llm_result = json.loads(cleaned_response)
                selected_apis = llm_result.get("selected_apis", [])
                unavailable_data = llm_result.get("unavailable_data", [])
                print(f"\nSuccessfully parsed {len(selected_apis)} selected APIs and {len(unavailable_data)} unavailable data types from LLM response")
                
                # Store selected APIs in state as Dict of endpoint: [limitation, reasoning]
                state.selected_api = {}
                for api in selected_apis:
                    endpoint = api.get("endpoint", "")
                    limitation = api.get("limitation", "")
                    reasoning = api.get("reasoning", "")
                    state.selected_api[endpoint] = [limitation, reasoning]
                
                # Store unavailable data in state as Dict of data_point: reason
                state.unavailable_data = {}
                for item in unavailable_data:
                    data_point = item.get("data_type", "Unknown")
                    reason = item.get("reason", "No reason provided")
                    state.unavailable_data[data_point] = reason
                
                if unavailable_data:
                    print("\nUnavailable Data:")
                    for data_point, reason in state.unavailable_data.items():
                        print(f"- {data_point}: {reason}")
                        
            except json.JSONDecodeError as e:
                print(f"Error parsing LLM response as JSON: {e}")
                print(f"Cleaned response: {cleaned_response}")
                selected_apis = []
                unavailable_data = []
                
        except Exception as e:
            print(f"Error calling OpenAI LLM: {e}")
            selected_apis = []
            unavailable_data = []
        
        print("="*60)
    
    # Step 6: LLM has already selected APIs and stored them in state.selected_api
    # No additional selection logic needed
    
    return state

def api_call_node(state: WbState):
    """API call node that fetches data for each selected API"""
    for endpoint, api_info in state.selected_api.items():
        if api_info and len(api_info) == 2:
            limitation, reasoning = api_info
            print(f"\n--- Fetching data for endpoint '{endpoint}' ---")
            print(f"Limitation: {limitation}")
            print(f"Reasoning: {reasoning}")
            
            # Find the db_id and idno for this endpoint from search results
            db_id = None
            idno = None
            
            for keyword, df in state.search_result.items():
                if not df.empty and 'db_id' in df.columns and 'idno' in df.columns:
                    # Look for rows where the endpoint matches (could be in name, idno, or other fields)
                    matching_rows = df[
                        (df['idno'] == endpoint) | 
                        (df['name'].str.contains(endpoint, case=False, na=False)) |
                        (df['db_id'].str.contains(endpoint, case=False, na=False))
                    ]
                    if not matching_rows.empty:
                        first_match = matching_rows.iloc[0]
                        db_id = first_match['db_id']
                        idno = first_match['idno']
                        print(f"Found matching API: DB={db_id}, IDNO={idno} for endpoint '{endpoint}'")
                        break
            
            if not db_id or not idno:
                print(f"Could not find db_id and idno for endpoint '{endpoint}', skipping...")
                continue
            
            # World Bank data API endpoint
            url = f"https://data360api.worldbank.org/data360/data?DATABASE_ID={db_id}&INDICATOR={idno}&skip=0"
            
            # Headers
            headers = {
                'accept': 'application/json'
            }
            
            try:
                # Make GET request
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                
                # Parse JSON response
                data = response.json()
                
                # Print the count
                if 'count' in data:
                    count = data['count']
                    print(f"Count for endpoint '{endpoint}': {count}")
                else:
                    print(f"No 'count' field found in response for endpoint '{endpoint}'")
                    count = 0
                
                # Print first 100 characters of response
                response_str = str(data)
                print(f"First 100 characters for endpoint '{endpoint}': {response_str[:100]}...")
                
                # Convert to DataFrame
                if 'value' in data and data['value']:
                    df = pd.DataFrame(data['value'])
                    print(f"Initial DataFrame for endpoint '{endpoint}': {len(df)} rows")
                else:
                    df = pd.DataFrame()
                    print(f"No data found for endpoint '{endpoint}'")
                
                # Handle pagination if count > 1000
                if count > 1000:
                    print(f"Fetching {count} total rows for '{endpoint}' (requires pagination)...")
                    skip = 1000
                    page_num = 2
                    
                    while skip < count:
                        # Make additional API call with incremented skip
                        paginated_url = f"https://data360api.worldbank.org/data360/data?DATABASE_ID={db_id}&INDICATOR={idno}&skip={skip}"
                        
                        try:
                            paginated_response = requests.get(paginated_url, headers=headers)
                            paginated_response.raise_for_status()
                            paginated_data = paginated_response.json()
                            
                            if 'value' in paginated_data and paginated_data['value']:
                                paginated_df = pd.DataFrame(paginated_data['value'])
                                df = pd.concat([df, paginated_df], ignore_index=True)
                                
                                # Only print progress every 10 pages
                                if page_num % 10 == 0 or skip + 1000 >= count:
                                    print(f"  Progress: {len(df)}/{count} rows fetched...")
                                page_num += 1
                            else:
                                break
                                
                        except requests.exceptions.RequestException as e:
                            print(f"  ❌ Error fetching page at skip={skip}: {e}")
                            break
                        except Exception as e:
                            print(f"  ❌ Unexpected error at skip={skip}: {e}")
                            break
                        
                        skip += 1000
                        time.sleep(0.5)  # Rate limiting
                
                # Store DataFrame in collected_data using endpoint as key
                state.collected_data[endpoint] = df
                print(f"✅ Final DataFrame for '{endpoint}': {df.shape[0]} rows × {df.shape[1]} columns")
                
            except requests.exceptions.RequestException as e:
                print(f"Error making API request for endpoint '{endpoint}': {e}")
            except Exception as e:
                print(f"Unexpected error for endpoint '{endpoint}': {e}")
            
            # Add slight pause between API calls
            time.sleep(0.5)
        else:
            print(f"Invalid API info for endpoint '{endpoint}': {api_info}")
    
    return state

# Main function
if __name__ == "__main__":
    # Initialize state with user query
    state = WbState()
    state.user_query = "What's the current inflation data and housing price data?"
    
    print("="*60)
    print("STARTING WB API PIPELINE")
    print("="*60)
    print(f"User Query: {state.user_query}")
    print("="*60)
    
    # Set default search keywords
    state.search_keyword = ['poverty', 'inflation']
    print(f"Using default search keywords: {state.search_keyword}")
    
    # Run the search node
    print("\n1. Running Search Node...")
    search_node(state)
    
    # Run the API selector node
    print("\n2. Running API Selector Node...")
    api_selector_node(state)
    
    # Run the API call node
    print("\n3. Running API Call Node...")
    api_call_node(state)
    
    # Print the final state
    print("\n" + "="*60)
    print("FINAL STATE:")
    print("="*60)
    print(f"User Query: {state.user_query}")
    print(f"Search Keywords: {state.search_keyword}")
    print(f"Search Results Keys: {list(state.search_result.keys())}")
    print(f"Selected APIs: {state.selected_api}")
    print(f"Collected Data Keys: {list(state.collected_data.keys())}")
    
    # Print detailed results for each keyword
    for keyword, result in state.search_result.items():
        print(f"\n--- DataFrame Results for '{keyword}' ---")
        if isinstance(result, pd.DataFrame) and not result.empty:
            print(result)
        else:
            print("No data available")
    
    print("="*60)

