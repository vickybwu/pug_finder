# Deploy Pug Finder for free (Streamlit Community Cloud)

1. Get a free Petfinder API key + secret: https://www.petfinder.com/developers/
2. Create a GitHub repo and push this folder (never commit secrets):
   ```
   cd ~/vickyasap/pug_finder
   git init && git add . && git commit -m "Pug Finder" && git branch -M main
   git remote add origin https://github.com/<you>/pug-finder.git
   git push -u origin main
   ```
3. Go to https://share.streamlit.io, sign in with GitHub, click **Create app**,
   pick the repo, branch `main`, main file `app.py`.
4. In **Advanced settings > Secrets**, paste:
   ```
   PETFINDER_KEY = "your_key"
   PETFINDER_SECRET=[REDACTED_PASSWORD]
   APP_PASSWORD = "optional-shared-password"   # delete this line for no password
   ```
5. Click **Deploy**. You'll get a URL like https://pug-finder.streamlit.app to share.

## Test locally first
```
pip install -r requirements.txt
streamlit run app.py      # shows sample data if no key is set
```
For local secrets, create `.streamlit/secrets.toml` with the same lines (it's gitignored).

## Notes
- The app sleeps after inactivity; the first visitor waits ~30s for it to wake.
- Results are cached 10 minutes to protect your Petfinder quota.
- To change criteria, edit criteria.yaml and push; the app redeploys automatically.
