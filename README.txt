CODEBOX NEXUS STUDIO
====================
See README_FA.md for the full Persian setup guide.

Quick start on Windows:
1. Extract the bundle.
2. Run Run_CodeBox_Server.bat and keep its terminal window open. Copy .env.example to .env and replace placeholder secrets before enabling Plus/OAuth/email codes.
3. Open http://127.0.0.1:8765, create an account, and sign in.
4. Run Build_CodeBox_EXE.bat to produce CodeBox_Free.exe and CodeBox_Plus.exe.
5. Plus downloads stay locked until the server grants plan=plus to an account.

The same Python server/database is used by the website and desktop app. Google/GitHub OAuth and email-code login require provider/SMTP configuration. Online deployment requires HTTPS, persistent storage, a strong stable secret, and a production WSGI server/reverse proxy.
