# Deploy Pug Finder for free (Streamlit Community Cloud)

No API keys are needed.

1. Push this folder to GitHub (https://github.com/vickybwu/pug_finder):
   ```
   cd ~/vickyasap/pug_finder
   git add -A
   git commit -m "Switch to web search"
   git push
   ```
2. On https://share.streamlit.io the app redeploys automatically after the push.
   (First time: Create app -> repo vickybwu/pug_finder, branch main, file app.py.)
3. Optional: to stop strangers using the app, go to Settings -> Secrets and add one line
   named ACCESS_CODE with a code of your choice in quotes. Visitors must enter it.
   You can delete the old Petfinder entries there.

## Notes
- The app sleeps when idle; the first visitor waits ~30s for it to wake.
- DuckDuckGo may rate-limit Streamlit's shared servers. If searches come back empty
  online, try again later or run locally.
- Results are cached for 10 minutes.
