# Pug Finder

Searches the web (DuckDuckGo, no API key needed) for pug listings, scrapes each result page,
filters them by `criteria.yaml`, and shows the matches.

## Setup
```
pip install -r requirements.txt
```

## Run from the command line
```
python pug_finder.py          # new matches only, opens results.html
python pug_finder.py --all    # every match
python pug_finder.py --demo   # offline test with sample_pages.json
```

## Run the web app
```
streamlit run app.py
```

## Files
- `pug_finder.py` - search, scrape, filter, results page
- `app.py` - Streamlit web page with a "Find pugs" button
- `criteria.yaml` - search phrases and match rules
- `sample_pages.json` - sample pages for the offline test
- `seen.json` - created automatically; remembers listings you've seen

## Limits
Details (age, sex, color, price) are guessed from page text and can be wrong.
Facebook, Craigslist and similar sites are skipped because they block scraping.
