import os
import time
import pandas as pd
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from dateutil import parser
import re
from tqdm import tqdm


BASE_URL = 'https://www.defense.gov/News/Contracts/?Page={}'
BASE_LINK = "http://www.defense.gov/News/Contracts/Contract/Article"
PAGES = 210


def parse_title(soup):
    """
    The Title looks like this in this in the html:
    
    '\r\n            \r\n            Contracts For Oct. 24, 2022\r\n            \r\n            \r\n        '
   
    This script grabs our text, filters it for the relevant strings, 
    and then algorithmically gets the information we need. Additionally, it is supported by 
    the parser.parse function from dateutil in Python.
    """
    
    title = soup.find("h1", {"class": "maintitle"}).text
    relevant_strings = list(filter(lambda c: len(c) > 2, title.split(' ')))
    date = ''
    for word in relevant_strings:
        if len(word) >= 2 and word != 'Contracts' and word != 'For':
            if word.isnumeric() and len(word) > 3:
                date = date + word
            else:
                word = word.replace(',', '')
                date = date + word + ' '

    date = parser.parse(date)
    date = date.strftime("%Y%m%d")
    return date


def check_for_many_companies(words):
    """
    This function walks through all of the words before the word 'award' is found. 
    If there are more than one word which looks like a Procurement ID (e.g. N6274223F9920),
    then this contract has multiple and we should treat the paragraph differently.
    
    Example Paragraph Where True:
    
    AOC Solutions Inc.,* Fairfax, Virginia (SP4704-23-A-0500); Blake Willson Group LLC,* doing business as BWG, 
    Arlington, Virginia (SP4704-23-A-0501); Integrated Finance and Accounting Solutions LLC,* Woodbridge, Virginia 
    (SP4704-23-A-0502); Lynch Consultants LLC,* Arlington, Virginia (SP4704-23-A-0503); MDC Global Solutions LLC,* Manassas, 
    Virginia (SP4704-23-A-0504); and New River Systems Corp.,* Ashburn, Virginia (SP4704-23-A-0505), are sharing 
    an estimated $181,125,713 firm-fixed-price blanket purchase agreement under solicitation SP4704-21-Q-0004 for 
    financial improvement and audit readiness support services. This was a competitive acquisition set aside for 
    service-disabled veteran-owned small businesses with 11 responses received. These are five-year contracts with no 
    option periods. Location of performance is Washington, D.C., with an Oct. 17, 2027, performance completion date. 
    Using customer is Defense Logistics Agency. Type of appropriation is fiscal 2023 through 2027 defense working capital 
    funds and various other funding. The contracting activity is the Defense Logistics Agency Contracting Services Office, 
    Richmond, Virginia.'
    
    """
    count = 0
    for word in words:
        if 'award' in word.lower():
            break
        for char in ['(', ')', '.', ',']:
            word = word.replace(char, '')
        if len(word) > 12 and word.isupper():
            count += 1

    if count > 1:
        return True
    else:
        return False

def check_for_correction(words, paragraph, date, corrections):
    """
    Sometimes, the paragraphs are not new contracts but just corrections. This function checks for this condition. 
    
    Example: 
    
    'Sikorsky Aircraft Corp., a Lockheed Martin Co., Stratford, Connecticut, is awarded a $39,920,367 firm-fixed-price modification 
    (P00001) to an order (N0001922F2491) against a previously issued basic ordering agreement (N0001919G0029).\xa0 This modification 
    adds scope to provide production and installation of a VH-92A Flight Training Device (FTD) and updates to a previously delivered 
    VH-92A FTD for the Marine Corps. Work will be performed in Binghamton, New York (49%); Orlando, Florida (17%); Stratford, 
    Connecticut (13%); Sterling, Virginia (10%); Quantico, Virginia (8%); Salt Lake City, Utah (1.5%); and various locations within 
    the continental U.S. (1.5%), and is expected to be completed in March 2024. Fiscal 2022 aircraft procurement (Navy) funds in the 
    amount of $8,869,507; and fiscal 2020 aircraft procurement (Navy) funds in the amount of $31,050,860 will be obligated at the 
    time of award, $31,050,860 of which will expire at the end of the current fiscal year. The Naval Air Systems Command, Patuxent 
    River, Maryland, is the contracting activity.'
    
    """
    for word in words[:10]:
        if 'correction' in word.lower() or 'update' in word.lower():
            corrections = pd.concat([corrections, pd.DataFrame({'Date': [date], 'Correction Paragraph': [paragraph]})], ignore_index=True)
            return corrections, True
    return corrections, False

def is_company_name(string):
    # Check if the string contains any capitalized words
    if not re.search(r'[A-Z]', string):
        return False

    # Check if the string consists solely of numbers or symbols
    if re.fullmatch(r'[^A-Za-z]*', string):
        return False

    return True

def has_six_digits(string):
    # Remove all commas from the string
    string = re.sub(r',', '', string)

    # Use a regular expression to search for 6 or more consecutive digit characters
    match = re.search(r'\d{6,}', string)
    if match:
        return True
    else:
        return False

def get_company_name(words):
    """
    This function walks through the list of words to find the company name. 
    This function uses the insight that company names are always the words before the first comma 
    in the paragraph. 
    
    Example of what the list of words looks like:
    ['Black', 'Construction-Tutor', 'Perini', 'JV,', 'Harmon,', 'Guam,', 'is', 'awarded', 'a', '$26,077,777', ...]
    
    Here, the function would return 'Black Construction-Tutor Perini JV. 
    """
    company_name = ''
    for word in words:
        if not has_six_digits(word):
            if ',' in word:
                company_name = company_name + word[:-1]
                for char in [',', '\r', '\n', '\t', '*']:
                    company_name.replace(char, '')
                break # End when this occurs
            elif 'and' in word or ' ' in word:
                company_name = company_name
            else:
                company_name = company_name + word + ' '
    
    return company_name

def extract_text_in_parentheses(text):
  # Use a regular expression to match the text within parentheses
  match = re.search(r'\(([^)]+)\)', text)
  # If a match is found, return the text within the parentheses
  if match:
    return match.group(1).replace(' ', '')
  # If no match is found, return an empty string
  else:
    return ""

def get_all_companies_info(companies):
    company_names = []
    company_contracts = []
    for company in companies:
        
        # ignore cases where it is like not just a name...
        if 'award' in company:
            company = company.split('award')[0]
        if len(company) < 110: 
            company_words = company + ' ' + extract_text_in_parentheses(company)
            company_words = company_words.split(' ')
            contract = get_contract(company_words)

            if len(contract) > 1:
                name = get_company_name(company_words)
                if name == '':
                    return [''], ['']
                company_names.append(name)
                company_contracts.append(contract)
            
    return company_names, company_contracts

def get_contract(words):
    """
    This function takes in all of the different words and checks for the first word that 
    """
    def _check_special_case(word):
        if word == '(FA4814‐':
            word = '(FA4814‐17‐C‐0002).'
            
    def _clean_word(word, chars):
        for char in chars:
            word = word.replace(char, '')
        return word
    
    def _format_contract(contract_key):
        if "-" not in contract_key:
            contract_key = contract_key[0:6] + '-' + contract_key[6:8] + '-' + contract_key[8:]
        if contract_key[-5].isupper():
            contract_key = contract_key[:-4] + '-' + contract_key[-4:]
        return contract_key
    
    contract_key = ''
    for word in words:
        _check_special_case(word)
        word = _clean_word(word = word, chars = ['(', ')', '.', ',', ' ', '‐', '-', '\r', '\n', '\xa0', '\t'])

        if (len(word) >= 12 or (len(word) == 11 and 'HEVA' in word)) and word.isupper() and '/' not in word:
            contract_key = _format_contract(contract_key=word)
            
        if len(word) >= 12 and word.isupper() and '/' in word and 'AN/' not in word:
            contract_key = get_contract(word.split('/'))

    return contract_key

def adjust_for_many_companies(amount, company_names):
    if amount != 'N/A' and amount != '':
        amount = int(int(amount) / len(company_names))
    return amount

def get_amount(words):
    """
    This function walks through the words and looks for first instance of a value with '$' in it. 
    This value is then cleaned and returned. 
    
    Example: 
    
    'Sikorsky Aircraft Corp., a Lockheed Martin Co., Stratford, Connecticut, 
    is awarded a $39,920,367 firm-fixed-price modification (P00001) ... ' 
    
    Would return: 39920367. 
    """
    amount = 'N/A'
    for word, nextword in zip(words, words[1:]):
        if '$' in word or '€' in word:
            amount = re.sub("[^0-9]", "", word)
            
            # Sometimes, there is a space between the symbol. This ensures we get the amount
            if amount == '': 
                amount = re.sub("[^0-9]", "", nextword)
            break

    if amount == 'N/A':
        # check for the word 'award'
        for i, word in enumerate(words):
            if 'award' in word:
                
                # now let's check the next three words for numbers. 
                first = re.sub("[^0-9]", "", words[i + 1])
                second = re.sub("[^0-9]", "", words[i + 2])
                try:
                    third = re.sub("[^0-9]", "", words[i + 3])
                except IndexError:
                    third = ''
                    
                
                end_amount = ''
                for word in [first, second, third]:
                    if len(word) > len(end_amount):
                        end_amount = word
                amount = end_amount
    
    return amount


def get_year(contract_key: str):
    """
    This function looks through the contract_key and grabs the first number after the first 
    '-' character. If the contract_key has been formatted correctly, this should always work. 
    
    key example: 'N68171-22-D-H009'. Year would be 22 = 2022. 
    """
    
    split_contract_key = contract_key.split('-')

    if contract_key == '':
        fiscal_year = 'N/A'
    else:
        fiscal_year = 'N/A'
        for row in split_contract_key:
            if len(row) == 2: 
                try: 
                    if 0<int(row)<100:
                        fiscal_year= row
                except ValueError:
                    ... 

    return fiscal_year


def is_contract_number(word):
    """
    """
    for char in ['(', ')', '.', ',', ';']:
        word = word.replace(char, '')
    if len(word) > 12 and word.isupper() and '/' not in word:
        pattern = r"^[A-Z0-9]{6}-\d{2}-\w{1,2}-\w{4}$"
        regex = re.compile(pattern)
        match = regex.search(word)
        if match:
            return True
    else:
        return False

def get_companies(words):
    """
    Walk through all of the words in a multiple company paragraph, check if one matches characters we expect as a contract
    and then add a ';' to it. Then, split the paragraph with ';' symbol. 
    """
    fixed_paragraph = ''
    for word in words:
        if is_contract_number(word):
            word = word[:-1] + ';'
        fixed_paragraph = fixed_paragraph + ' ' + word

    return fixed_paragraph.split(';')

def parse_out(soup, link, results, corrections):
    
    def _check_valid_year(year, contract_key):
        if year == 'N/A':
            contract_key = 'N/A'
        return contract_key
    
    
    def _get_relevant_paragraphs_from_soup(soup):
        content = soup.find(
            "div", {"class": "adetail abanner no-abanner-mobile aframe content-type-400"})
        ps = content.find_all("p") 
        paragraphs = list(filter(lambda p: len(p.text) > 200, ps))
        relevant_paragraphs = [p.text for p in paragraphs]
        
        end_relevant_paragraphs = []
        for paragraph in relevant_paragraphs:
            paragraphs = paragraph.split('\n\n')
            for p in paragraphs:
                if len(p) > 200:
                    end_relevant_paragraphs.append(p)
        
        return end_relevant_paragraphs
    
    date = parse_title(soup)        
    relevant_paragraphs = _get_relevant_paragraphs_from_soup(soup)
    
    for paragraph in relevant_paragraphs:
        words = paragraph.split(' ')
        corrections, is_correction = check_for_correction(words, paragraph, date, corrections)
        if is_correction:
            continue
        if check_for_many_companies(words):
            company_names = []
            company_contracts = []

            companies = get_companies(words)
            company_names, company_contracts = get_all_companies_info(companies)
            if company_names == ['']:
                continue

            if len(company_names) > 0 and len(company_contracts) > 0:
                amount = get_amount(words)
                amount = adjust_for_many_companies(amount, company_names)
        
                for i in range(len(company_names)):
                    year = get_year(company_contracts[i])
                    procurment_id = company_contracts[0][:-4] + company_contracts[i][-4:]
                    results = pd.concat([results,pd.DataFrame({'Date': [date], 
                                            'FY': [year], 
                                            'Company': [company_names[i]],
                                            'Dollar Amount': [amount], 
                                            'ProcurementID': [procurment_id], 
                                            'Link': [link]})], 
                                        ignore_index=True)
       
       
        else:

            company_name = get_company_name(words)
            amount = get_amount(words)
            contract_key = get_contract(words)
            year = get_year(contract_key)
            contract_key = _check_valid_year(year, contract_key)
            
            results = pd.concat([results,pd.DataFrame({'Date': [date], 
                                         'FY': [year], 
                                         'Company': [company_name],
                                         'Dollar Amount': [amount], 
                                         'ProcurementID': [contract_key], 
                                         'Link': [link]})], 
                                     ignore_index=True)

    return results, corrections


 

def main():
    results = pd.DataFrame(columns=['Date', 'FY', 'Company', 'Dollar Amount', 'ProcurementID', 'Link'])
    corrections = pd.DataFrame(columns=['Date', 'Correction Paragraph'])

    
    directory = 'page_htmls'
    for file in tqdm(os.listdir(directory)):
        if 'html' in file:
            fp = os.path.join(directory, file)
            with open(fp) as f:
                soup = BeautifulSoup(f, "html.parser")
            
            link = 'http://www.defense.gov/News/Contracts/Contract/Article/' + file.split('.html')[0] + '/'
            results, corrections = parse_out(soup, link, results, corrections)
            
    results.to_csv('webscraped_data.csv', index=False)
    corrections.to_csv('correction.csv', index=False)

if __name__ == "__main__":
    main()
