@echo off
echo Configuring User...
git config --global user.email "rahulsharwa2020@gmail.com"
git config --global user.name "Rahulsharwa"

echo Initializing Repository...
git init
git remote add origin git@github.com:Rahulsharwa/BusinessCardExtr.git

echo Adding Files...
git add .
git commit -m "Initial commit of Business Card Extractor"
git branch -M main

echo Pushing to GitHub...
git push -u origin main

pause
