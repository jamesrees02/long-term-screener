# Long-Term Stock Screener

A simple screener for long-term investment research (not day-trading):

- Pick Finviz fundamental filters (P/E, dividend yield, sector, ROE, debt
  ratios, and more) with real from/to sliders.
- See results in a table where you choose which columns to show and in
  what order.
- Click a stock in the results to open a daily/weekly candlestick chart
  (Yahoo Finance data), in the same style as TradingView.

## Running it locally (for testing/development only)

You need Python installed. Then, from this folder:

```
pip install -r requirements.txt
streamlit run app.py
```

This opens the app at `http://localhost:8501` in your browser. Close the
terminal window to stop it — nothing stays running in the background.

## Putting it on the web (so anyone can use it with just a link)

This uses **Streamlit Community Cloud**, which hosts the app for free.
Once deployed, using the app only ever requires opening the web link —
no installs, no local process, works from a phone or any computer.

1. **Create a GitHub repository** and push this folder's contents to it.
   - If you don't already have a repo for this: go to
     [github.com/new](https://github.com/new), name it (e.g.
     `long-term-screener`), and create it.
   - From this folder, run:
     ```
     git init
     git add .
     git commit -m "Initial version of the screener"
     git branch -M main
     git remote add origin <the URL GitHub gives you>
     git push -u origin main
     ```
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   your GitHub account (one click, no new password to create).
3. Click **"New app"**, pick the repository you just pushed, set the
   branch to `main` and the main file path to `app.py`, then click
   **Deploy**.
4. After a minute or two you'll get a permanent URL like
   `https://your-app-name.streamlit.app`. That's the link to bookmark and
   share — visiting it never requires a GitHub login.

**One thing to know:** if the app isn't visited for about a week, Streamlit
puts it to sleep to save resources. The next visit takes ~10-20 seconds to
wake back up, then it runs normally. This is expected and free of charge.

### Updating the app later

Any time you want to change something: edit the files, then run
`git add .`, `git commit -m "..."`, `git push` — Streamlit Community Cloud
automatically redeploys the new version within a minute or two.
