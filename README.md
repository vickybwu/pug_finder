# Pug Finder

Finds pugs for adoption on Petfinder that match `criteria.yaml`, writes `results.html`, and opens it in your browser.

## Setup
```
pip install -r requirements.txt
export PETFINDER_KEY=your_key
export PETFINDER_SECRET=your_secret   # free at https://www.petfinder.com/developers/
```

## Run
```
python pug_finder.py          # new matches only
python pug_finder.py --all    # every match
python pug_finder.py --demo   # offline test with sample_listings.json
python pug_finder.py --no-open  # don't open the browser
```

## Files
- `pug_finder.py` - the script
- `criteria.yaml` - your criteria (male, young / about 1-3 years, fawn or apricot, healthy, US)
- `sample_listings.json` - sample data for `--demo`
- `seen.json` - created automatically; tracks listings you've already seen
