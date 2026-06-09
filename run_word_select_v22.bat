@echo off
cd /d C:\Users\user1\Documents\IT\PDF_to_HTML
python generate_pdf_word_select_v22.py
python -m http.server 8000
