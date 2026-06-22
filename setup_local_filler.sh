#!/bin/bash

# ─────────────────────────────────────────────
#  Local Form Filler — Setup Script
#  Double-click this once to install everything
# ─────────────────────────────────────────────

echo "Setting up Local Form Filler..."

# Check Python
if ! command -v python3 &>/dev/null; then
  osascript -e 'display alert "Python not found" message "Please install Python from python.org first." as critical'
  exit 1
fi

# Install required packages
echo "Installing dependencies (this happens once)..."
pip3 install playwright requests --quiet

# Install the Playwright browser
echo "Installing Chromium browser for automation (this may take a minute)..."
python3 -m playwright install chromium

osascript -e 'display notification "Setup complete! Now edit local_form_filler.py with your Render URL and CV path." with title "Job Agent"'
echo ""
echo "✅ Setup complete!"
echo ""
echo "NEXT STEPS:"
echo "1. Open local_form_filler.py in a text editor"
echo "2. Replace RENDER_API_URL with your actual Render URL"
echo "3. Replace CV_PATH with the path to your CV file on this Mac"
echo "4. Save and run: python3 local_form_filler.py"
echo ""
