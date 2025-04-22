# StateMachineNexusAutoDL
This is a state machine version of [NexusAutoDL](https://github.com/jaylann/NexusAutoDL), designed for automating the process of downloading mods from [Nexusmods](https://www.nexusmods.com/), without being a premium member. 
Literally the same functional, but a little more robust. It also auto closes broser tabs (at least, really tries to) so you dont need to manually close them, as well as have 9000GB+ of ram. However, it requires some specific setup for beter clicking accuracy. 

# With this script
You can start downloading 9999+ mods collection at night and simply go to sleep - it shall be done tomorrow. You need to check if it works first ofc, and, if you are not sure if this pice of code have some potential treat to your pc, read source code (sorry for zero readability). 

The main purpose of rewriting [NexusAutoDL](https://github.com/jaylann/NexusAutoDL) and not using similar projects on github/somewhere else is really low accuracy of existing projects. 1 - most of them based on sift. Its overkill for finding buttons, they will be never rotated even in 2d, so they just leading to false positives. A lot of. 2 - they just scanning for all known buttons every time. It also leads to false positives. With state machine and much simplier and robust `cv2.matchTemplate` the main issues are gone. Also it will close browser tab keeping 2 open tabs in ram - not all 9999+ tabs. The next step is only to use full ai agent based solution, but if you can afford THAT, then just go buy nexus subscription. It really not worth any of it


# Prerequisites
Miniconda/anaconda of any version, Windows 10+, should run on potato

# Setup
First, open your vortex, make the window as small as possible, and move it at the top\bottom left\right corner as you like. Then, if you want to see terminal, move it under vortex window. 
And finnaly, open browser you going to use, and move it to the side of your desktop. It should look just like this

[potato](./screenshoot.png)

Then, you can close browser. Script will open new broswer window, the purpose of openning it manually is for remembering browser position

The basic button templates assumes that you have classic vortex theme, and standart nexusmods dark theme (idk if they even have white theme). If you are using different vortex theme or browser extension in browser that change colors, set it as described or go to `assets` folder and replace existing image with your own screenshots. 
Note, this script compares images RGB (actually brg but it doesnt matter at all) values and it will not convert them to grayscale. This is done due minimization of false positives. If something not working as expected, adjust parameters as described under Adjusting parameters.


# Running the Script

## Using prebuild exe

With cmd
`smnexusautodl.exe <arguments>`
With powershell
`./smnexusautodl.exe <arguments>`



## Running source code

Create and activate conda env

`conda create --name nexusautodl  -c conda-forge python=3.9`
`conda activate nexusautodl`

Clone this repository:

`git clone https://github.com/Mimocro/SMNexusAutoDL`

Or manually download the repository.

Then go into the directory you cloned/downloaded to.

`cd SMNexusAutoDL`

Install all necessary packages.

`pip install -r requirements.txt`

Run python script with or without arguments.

Windows:
`python main.py <arguments>`

Basic command that you can copypaste if you using firefox and vortex:
`python main.py --browser firefox --vortex  --verbose `


# Command Line Options

`--browser <browserName>`: selects browser to open and move to work with Vortex. Can only be used in combination with `--vortex`. Currently supported browsers: “chrome”, “firefox” and "edge" (limited and untested)
`--vortex`: specifies use with Vortex mod manager: i have not tested it with any other mod manager, but it should work i think
`--verbose`: prints verbose output
`--force-primary`: forces a system with multiple monitors to only be scanned on it’s primary display
`--vortex-dl-match-threshold <float>`: Match threshold for Vortex download button (default: 0.9)
`--vortex-cont-match-threshold <float>`: Match threshold for Vortex continue button (default: 0.9)
`--web-dl-match-threshold <float>`: Match threshold for web download button (default: 0.8)
`--click-here-match-threshold <float>`: Match threshold for "click here" button (default: 0.9)
`--understood-match-threshold <float>`: Match threshold for "understood" button (default: 0.9)
`--staging-match-threshold <float>`: Match threshold for staging button (default: 0.9)
`--wait-timeout-vortex <seconds>`: Timeout (s) for Vortex-related waits (default: 7.0)
`--wait-timeout-web <seconds>`: Timeout (s) for web-related waits (default: 4.0)
`--wait-timeout-click-here <seconds>`: Timeout (s) for "click here" waits (default: 6.0)
`--scan-interval-vortex <seconds>`: Scan interval (s) for Vortex actions (default: 0.2)
`--scan-interval-web <seconds>`: Scan interval (s) for web actions (default: 0.5)
`--scan-interval-click-here <seconds>`: Scan interval (s) for "click here" actions (default: 0.5)
`--post-click-delay <seconds>`: Delay (s) after click before restarting scan (default: 2.0)


# Adjusting parameters
If script makes too much false positive clicks or not clicking at all, you can change
1) Images under assets folder:
- Make and crop screenshot of the button that script fails to click
- Replace file in `assets` folder with your own. There is some notes from source code
```BUTTON_ASSETS = {
    "vortex_dl": ["VortexDownloadButton.png", "VortexDownloadButton2.png", "VortexDownloadButton3.png"], #vortex download button
    "web_dl": ["WebsiteDownloadButton.png", "WebsiteDownloadButton2.png", "WebsiteDownloadButton3.png"], #slow download button in nexus site
    "click_here": ["ClickHereButton.png", "ClickHereButton2.png", "ClickHereButton3.png"], #click here button in nexus site (just for sure)
    "vortex_cont": ["VortexContinueButton.png", "VortexContinueButton2.png", "VortexContinueButton3.png"], #continue button for a case when vortex asks if it ned to redownload mod
    "understood": ["UnderstoodButton.png", "UnderstoodButton2.png", "UnderstoodButton3.png"], 
    "staging": ["StagingButton.png", "StagingButton2.png", "StagingButton3.png"]
}```


2) Change THRESHOLD values:
- See Command Line Options. 
- Increase/decrease values of the specific buttons based on accuracy of the script.
- For exp, if there is too many false positive clicks with download button at vortex, decrease to something like `--vortex-dl-match-threshold 0.95`. In reverse, if it fails to find this button, decrease it to `--vortex-dl-match-threshold 0.8` or lower - or try to make your own screenshoot as described early.

3) Change timeouts
My setup is ssd and not that bad cpu, 300 mb\sec (yeah) internet. It opens the browser tab in like 1 second. If script works too chaotic, adjust timeouts (increase them). If you have NASA pc, and you want faster speed, mess with this values and it will be ~2 times faster or so. 

# Demo
[potato](./demo.mp4)

# Credit
Credit goes to [NexusAutoDL](https://github.com/jaylann/NexusAutoDL) for being solid base for this project.

# Disclaimer
Nexusmods TOS state that using an automated program to download mods is prohibited. By using this software you are doing so at your own risk. The Author is not responsible for any kind of consequences and damages that might occur by using this program.
Also, if it will somehow decide to delete Windows or System32 folder, perhaps, this is the only fate..
