# NetOverlay
A proof-of-concept Python script demonstrating networked overlay using a "client-server model" (based on wise words from Snipcola).
This project was built for fun and as a way to experiment with networking between 2 computers, originally started off as AI cheats.

# Overview
The idea of this project is to minimise the usage on the client (game) machine. The only responsibility is to read game memory and to render the overlay.
All the "heavy lifting" is done by the server PC, e.g. calculations, entity processing, etc...

# Architecture
The system is split into two scripts:
  - ``server.py``
    - Listens for incoming data from client
    - Receives game information (e.g.: player positions, viewmatrix)...
    - Performs necessary calculations to determine what needs to be drawn on client
    - Sends back the drawing instructions to client
  - ``client.py``
    - Reads game memory
    - Sends data to server on each frame
    - Waits for drawing instructions from the server
    - Renders the visuals (gui, esp, etc...) in an overlay window via PyQt
   
# Usage
1. Configuration:
  - Open ``server.py`` and ``client.py`` in your preferred code/text editor
  - In ``client.py``, set ``UDP_IP_SERVER`` to the server PC's IP (server listens to anything coming from the ports defined, no need to change anything on that side)

2. Run:
  - Run ``server.py`` on the server PC. As stated above, it'll start listening to any incoming connection on the ports defined.
  - Run ``client.py`` on the client PC. It will attempt to connect to the server & game.

# Disclaimer
This project is intended for educational purposes only. It is a proof-of-concept to demonstrate networking and client-server architecture. The user assumes all responsibility for use of the software. Support, or any form of help will not be provided.

# Credits
- [Read1dno/CS2ESP-external-cheat](https://github.com/Read1dno/CS2ESP-external-cheat/blob/main/CS2ESP.py) - ESP
- [Snipcola/ProExt](https://github.com/snipcola/ProExt) - Inspiration, help, witnessing the final line being written
- AI used for partial help with understanding stuff, light debugging before I was going to trash the project and go to sleep
