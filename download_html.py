import time
import os
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

BASE_URL = 'https://www.defense.gov/News/Contracts/?Page={}'
BASE_LINK = "http://www.defense.gov/News/Contracts/Contract/Article"
PAGES = 211

def set_up_driver():
    """
    Set up the chrome web driver with the settings that we want.
    """
    options = Options()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--incognito')
    options.add_argument('--headless')
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_links(page_url: str):
    """
    This function sets up the google headless driver and grabs the soup for a page_url.
    It returns the list of valid links for searching.  
    """
    # Set up Driver
    driver = set_up_driver()
    driver.get(page_url)
    elem = driver.find_element("xpath", "//*")
    source_code = elem.get_attribute("outerHTML")
    
    # Go Through HTML and grab the relevant links
    soup = BeautifulSoup(source_code, 'html.parser')
    possible_links = [x.get('href') for x in soup.find_all('a')]
    filtered_links = []
    for possible_link in possible_links:
        if possible_link is not None and BASE_LINK in possible_link:
            filtered_links.append(possible_link)
            
    return filtered_links

def get_html_save_path(link: str):
    """
    Takes in a link name and grabs only the information we need for 
    saving it later into some html file. 
    
    e.g. 'http://www.defense.gov/News/Contracts/Contract/Article/3251958/'
    turns into '3251958.html'
    """
    
    return 'page_htmls/' + ''.join(link.split('/')[-2:]) + '.html'
    
def main():
    
    # Iterate through the pages and get all of the repsective links
    for i in tqdm(range(PAGES), position=0, leave=True):
        page_url = BASE_URL.format(i + 1)
        print(f"******{page_url}******", end='\r')
        
        
        links = get_links(page_url)
        
        for link in links:
            save_path = get_html_save_path(link)            
            if not os.path.exists(save_path):
                try: 
                    r = requests.get(link)           
                except:
                    print("[INFO] We got a weird error. Sleeping for 30 seconds")
                    time.sleep(30)
                    r = requests.get(link)
                        
        
                
                with open(save_path, "w") as f:
                    f.write(r.text)
            else:
                print(f"[INFO] Already Downloaded and Saved: {save_path}")


if __name__ == "__main__":
    main()