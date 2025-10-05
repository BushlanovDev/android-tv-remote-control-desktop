<div align="center">
    <h1>📺 Android TV Remote Control Desktop</h1>
    <p>Cross-platform desktop application for controlling Android TV</p>

[![Actions status](https://github.com/BushlanovDev/android-tv-remote-control-desktop/actions/workflows/check.yml/badge.svg)](https://github.com/BushlanovDev/android-tv-remote-control-desktop/actions) 
[![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen)](https://www.python.org/downloads/)
[![PyQt](https://img.shields.io/badge/PyQt-5.15.11-brightgreen)](https://pypi.org/project/PyQt5/) 
[![Platform Win32 | Linux | macOS](https://img.shields.io/badge/Platform-Win32%20|%20Linux%20|%20macOS-brightgreen)]() 
[![MIT license](http://img.shields.io/badge/license-MIT-brightgreen.svg)](http://opensource.org/licenses/MIT) 
</div>


## 🌟 Description
**Attention!** This program can ONLY control Android TVs! To do this, the application and the TV must be in the same local network!  
The application scans your network and connects to the found android TV.  
It happens that the first attempt fails to find the TV, try pressing the search button again.  
At the moment, the remote control has all the basic control capabilities, such as volume control, channel switching, menu calling and turning off the TV.
<div align="center">
  <img src="https://github.com/BushlanovDev/android-tv-remote-control-desktop/blob/main/resources/screenshot.png?raw=true" alt="Android TV Remote Control Desktop Screenshot" width="800" />
</div>

## 🚀 Quick Start
Download the executable file for your platform from the [release page](https://github.com/BushlanovDev/android-tv-remote-control-desktop/releases) and enjoy =)

## 💻 Run from source code
```bash
# Clone project 
git clone https://github.com/BushlanovDev/android-tv-remote-control-desktop.git

# Create and activate virtual venv 
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run app
python main.py
```

## 🛠️ Building an executable file
```bash
pip install pyinstaller # or pip install auto-py-to-exe for use gui

pyinstaller --noconfirm --onedir --windowed --icon "./resources/icon32.ico" --hidden-import "zeroconf._utils.ipaddress" --hidden-import "zeroconf._handlers.answers"  "./main.py"
```

## 📄 License

This repository's source code is available under the [MIT License](LICENSE).
