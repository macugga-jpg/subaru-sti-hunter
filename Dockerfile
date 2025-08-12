touch Dockerfile
FROM python:3.12-slim

Install dependencies for Chromium and chromedriver

RUN apt-get update && apt-get install -y 
chromium 
chromium-driver 
--no-install-recommends 
&& rm -rf /var/lib/apt/lists/*

Set environment variables for Selenium

ENV CHROME_BIN=/usr/bin/chromium ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver ENV PATH="/usr/bin:${PATH}"

WORKDIR /app COPY requirements.txt . RUN pip install --no-cache-dir -r requirements.txt COPY . . CMD ["python", "sti_hunter_bot.py"]
