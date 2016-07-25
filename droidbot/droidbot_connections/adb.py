# This is the interface for adb
__author__ = 'liyc'
import subprocess
import logging
import re


class ADBException(Exception):
    """
    Exception in ADB connection
    """
    pass


class ADB(object):
    """
    interface of ADB
    send adb commands via this, see:
    http://developer.android.com/tools/help/adb.html
    """
    UP = 0
    DOWN = 1
    DOWN_AND_UP = 2

    def __init__(self, device):
        """
        initiate a ADB connection from serial no
        the serial no should be in output of `adb devices`
        :param device: instance of Device
        :return:
        """
        self.logger = logging.getLogger('ADB')
        self.device = device
        self.cmd_prefix = ['adb']
        self.shell = None

        r = subprocess.check_output(['adb', 'devices']).split('\n')
        if not r[0].startswith("List of devices attached"):
            raise ADBException()

        online_devices = []
        for line in r[1:]:
            if not line:
                continue
            segments = line.split("\t")
            if len(segments) != 2:
                continue
            if segments[1] == "device":
                online_devices.append(segments[0])

        if not online_devices:
            raise ADBException()

        if device.serial:
            if not device.serial in online_devices:
                raise ADBException()
        else:
            device.serial = online_devices[0]

        self.cmd_prefix.append("-s")
        self.cmd_prefix.append(device.serial)

        if self.check_connectivity():
            self.logger.info("adb successfully initiated, the device is %s" % device.serial)
        else:
            raise ADBException()

    def run_cmd(self, extra_args):
        """
        run an adb command and return the output
        :return: output of adb command
        """
        if isinstance(extra_args, str):
            extra_args = extra_args.split()
        assert isinstance(extra_args, list)

        args = [] + self.cmd_prefix
        args += extra_args

        self.logger.debug('command:')
        self.logger.debug(args)
        r = subprocess.check_output(args)
        self.logger.debug('return:')
        self.logger.debug(r)
        return r

    def shell(self, extra_args):
        """
        run an `adb shell` command
        @param extra_args:
        @return: output of adb shell command
        """
        if isinstance(extra_args, str):
            extra_args = extra_args.split()
        assert isinstance(extra_args, list)

        shell_extra_args = ['shell'] + extra_args
        return self.run_cmd(shell_extra_args)

    def check_connectivity(self):
        """
        check if adb is connected
        :return: True for connected
        """
        r = self.run_cmd("get-state")
        return r.startswith("device")

    def disconnect(self):
        """
        disconnect adb
        """
        self.logger.info("disconnected")

    from com.dtmilano.android import viewclient

    def getDisplayInfo(self):
        displayInfo = self.getLogicalDisplayInfo()
        if displayInfo:
            return displayInfo
        displayInfo = self.getPhysicalDisplayInfo()
        if displayInfo:
            return displayInfo
        self.logger.error("Error getting display info")
        return None

    def getLogicalDisplayInfo(self):
        """
        Gets C{mDefaultViewport} and then C{deviceWidth} and C{deviceHeight} values from dumpsys.
        This is a method to obtain display logical dimensions and density
        """
        logicalDisplayRE = re.compile(".*DisplayViewport\{valid=true, .*orientation=(?P<orientation>\d+),"
                                      " .*deviceWidth=(?P<width>\d+), deviceHeight=(?P<height>\d+).*")
        for line in self.shell("dumpsys display").splitlines():
            m = logicalDisplayRE.search(line, 0)
            if m:
                displayInfo = {}
                for prop in ["width", "height", "orientation"]:
                    displayInfo[prop] = int(m.group(prop))
                for prop in ["density"]:
                    d = self.getDisplayDensity(None, strip=True, invokeGetPhysicalDisplayIfNotFound=True)
                    if d:
                        displayInfo[prop] = d
                    else:
                        # No available density information
                        displayInfo[prop] = -1.0
                return displayInfo
        return None

    def getPhysicalDisplayInfo(self):
        """
        Gets C{mPhysicalDisplayInfo} values from dumpsys. This is a method to obtain display dimensions and density
        """
        phyDispRE = re.compile("Physical size: (?P<width>\d+)x(?P<height>\d+).*"
                               "Physical density: (?P<density>\d+)", re.MULTILINE)
        data = self.shell("wm size") + self.shell("wm density")
        m = phyDispRE.search(data)
        if m:
            displayInfo = {}
            for prop in ["width", "height"]:
                displayInfo[prop] = int(m.group(prop))
            for prop in ["density"]:
                displayInfo[prop] = float(m.group(prop))
            return displayInfo
        phyDispRE = re.compile(
            ".*PhysicalDisplayInfo{(?P<width>\d+) x (?P<height>\d+), .*, density (?P<density>[\d.]+).*")
        for line in self.shell("dumpsys display").splitlines():
            m = phyDispRE.search(line, 0)
            if m:
                displayInfo = {}
                for prop in ["width", "height"]:
                    displayInfo[prop] = int(m.group(prop))
                for prop in ["density"]:
                    # In mPhysicalDisplayInfo density is already a factor, no need to calculate
                    displayInfo[prop] = float(m.group(prop))
                return displayInfo
        # This could also be mSystem or mOverscanScreen
        phyDispRE = re.compile("\s*mUnrestrictedScreen=\((?P<x>\d+),(?P<y>\d+)\) (?P<width>\d+)x(?P<height>\d+)")
        # This is known to work on older versions (i.e. API 10) where mrestrictedScreen is not available
        dispWHRE = re.compile("\s*DisplayWidth=(?P<width>\d+) *DisplayHeight=(?P<height>\d+)")
        for line in self.shell("dumpsys window").splitlines():
            m = phyDispRE.search(line, 0)
            if not m:
                m = dispWHRE.search(line, 0)
            if m:
                displayInfo = {}
                BASE_DPI = 160.0
                for prop in ["width", "height"]:
                    displayInfo[prop] = int(m.group(prop))
                for prop in ["density"]:
                    d = 0
                    if displayInfo and "density" in displayInfo:
                        d = displayInfo["density"]
                    else:
                        _d = self.shell("getprop ro.sf.lcd_density").strip()
                        if _d:
                            d = float(_d) / BASE_DPI
                        else:
                            _d = self.shell("getprop qemu.sf.lcd_density").strip()
                            if _d:
                                d = float(_d) / BASE_DPI
                    if d:
                        displayInfo[prop] = d
                    else:
                        # No available density information
                        displayInfo[prop] = -1.0
                return displayInfo
        return None

    def getFocusedWindow(self):
        """
        Get the focused window
        """
        for window in self.getWindows().values():
            if window.focused:
                return window
        return None

    def getFocusedWindowName(self):
        """
        Get the focused window name
        """
        window = self.getFocusedWindow()
        if window:
            return window.activity
        return None

    def getWindows(self):
        windows = {}
        dww = self.shell("dumpsys window windows")
        lines = dww.splitlines()
        widRE = re.compile("^ *Window #%s Window{%s (u\d+ )?%s?.*}:" %
                           (_nd("num"), _nh("winId"), _ns("activity", greedy=True)))
        currentFocusRE = re.compile("^  mCurrentFocus=Window{%s .*" % _nh("winId"))
        viewVisibilityRE = re.compile(" mViewVisibility=0x%s " % _nh("visibility"))
        # This is for 4.0.4 API-15
        containingFrameRE = re.compile("^   *mContainingFrame=\[%s,%s\]\[%s,%s\] mParentFrame=\[%s,%s\]\[%s,%s\]" %
                                       (_nd("cx"), _nd("cy"), _nd("cw"), _nd("ch"), _nd("px"), _nd("py"), _nd("pw"),
                                        _nd("ph")))
        contentFrameRE = re.compile("^   *mContentFrame=\[%s,%s\]\[%s,%s\] mVisibleFrame=\[%s,%s\]\[%s,%s\]" %
                                    (_nd("x"), _nd("y"), _nd("w"), _nd("h"), _nd("vx"), _nd("vy"), _nd("vx1"),
                                     _nd("vy1")))
        # This is for 4.1 API-16
        framesRE = re.compile("^   *Frames: containing=\[%s,%s\]\[%s,%s\] parent=\[%s,%s\]\[%s,%s\]" %
                              (_nd("cx"), _nd("cy"), _nd("cw"), _nd("ch"), _nd("px"), _nd("py"), _nd("pw"), _nd("ph")))
        contentRE = re.compile("^     *content=\[%s,%s\]\[%s,%s\] visible=\[%s,%s\]\[%s,%s\]" %
                               (_nd("x"), _nd("y"), _nd("w"), _nd("h"), _nd("vx"), _nd("vy"), _nd("vx1"), _nd("vy1")))
        policyVisibilityRE = re.compile("mPolicyVisibility=%s " % _ns("policyVisibility", greedy=True))

        currentFocus = None

        for l in range(len(lines)):
            m = widRE.search(lines[l])
            if m:
                num = int(m.group("num"))
                winId = m.group("winId")
                activity = m.group("activity")
                wvx = 0
                wvy = 0
                wvw = 0
                wvh = 0
                px = 0
                py = 0
                visibility = -1
                policyVisibility = 0x0
                sdkVer = self.getSDKVersion()

                for l2 in range(l + 1, len(lines)):
                    m = widRE.search(lines[l2])
                    if m:
                        l += (l2 - 1)
                        break
                    m = viewVisibilityRE.search(lines[l2])
                    if m:
                        visibility = int(m.group("visibility"))
                    if sdkVer >= 17:
                        wvx, wvy = (0, 0)
                        wvw, wvh = (0, 0)
                    if sdkVer >= 16:
                        m = framesRE.search(lines[l2])
                        if m:
                            px, py = obtainPxPy(m)
                            m = contentRE.search(lines[l2 + 1])
                            if m:
                                # FIXME: the information provided by 'dumpsys window windows' in 4.2.1 (API 16)
                                # when there's a system dialog may not be correct and causes the View coordinates
                                # be offset by this amount, see
                                # https://github.com/dtmilano/AndroidViewClient/issues/29
                                wvx, wvy = obtainVxVy(m)
                                wvw, wvh = obtainVwVh(m)
                    elif sdkVer == 15:
                        m = containingFrameRE.search(lines[l2])
                        if m:
                            px, py = obtainPxPy(m)
                            m = contentFrameRE.search(lines[l2 + 1])
                            if m:
                                wvx, wvy = obtainVxVy(m)
                                wvw, wvh = obtainVwVh(m)
                    elif sdkVer == 10:
                        m = containingFrameRE.search(lines[l2])
                        if m:
                            px, py = obtainPxPy(m)
                            m = contentFrameRE.search(lines[l2 + 1])
                            if m:
                                wvx, wvy = obtainVxVy(m)
                                wvw, wvh = obtainVwVh(m)
                    else:
                        log.warning("Unsupported Android version %d" % sdkVer)

                    # print >> sys.stderr, "Searching policyVisibility in", lines[l2]
                    m = policyVisibilityRE.search(lines[l2])
                    if m:
                        policyVisibility = 0x0 if m.group("policyVisibility") == "true" else 0x8

                windows[winId] = Window(num, winId, activity, wvx, wvy, wvw, wvh, px, py, visibility + policyVisibility)
            else:
                m = currentFocusRE.search(lines[l])
                if m:
                    currentFocus = m.group("winId")

        if currentFocus in windows and windows[currentFocus].visibility == 0:
            windows[currentFocus].focused = True

        return windows

    def __transformPointByOrientation(self, (x, y), orientationOrig, orientationDest):
        if orientationOrig != orientationDest:
            if orientationDest == 1:
                _x = x
                x = self.getDisplayInfo()["width"] - y
                y = _x
            elif orientationDest == 3:
                _x = x
                x = y
                y = self.getDisplayInfo()["height"] - _x
        return (x, y)

    def getOrientation(self):
        displayInfo = self.getDisplayInfo()

        if "orientation" in displayInfo:
            return displayInfo["orientation"]

        surfaceOrientationRE = re.compile("SurfaceOrientation:\s+(\d+)")
        output = self.shell("dumpsys input")
        m = surfaceOrientationRE.search(output)
        if m:
            return int(m.group(1))
        return -1

    def unlock(self):
        """
        Unlock the screen of the device
        """
        self.shell("input keyevent MENU")
        self.shell("input keyevent BACK")

    def press(self, key_code):
        """
        Press a key
        """
        self.shell("input keyevent %s" % key_code)

    def touch(self, x, y, orientation=-1, eventType=DOWN_AND_UP):
        if orientation == -1:
            orientation = self.getOrientation()
        self.shell("input tap %d %d" % self.__transformPointByOrientation((x, y), orientation, self.display["orientation"]))

    def longTouch(self, x, y, duration=2000, orientation=-1):
        """
        Long touches at (x, y)
        @param duration: duration in ms
        @param orientation: the orientation (-1: undefined)
        This workaround was suggested by U{HaMi<http://stackoverflow.com/users/2571957/hami>}
        """
        self.drag((x, y), (x, y), duration, orientation)

    def drag(self, (x0, y0), (x1, y1), duration, steps=1, orientation=-1):
        """
        Sends drag event n PX (actually it's using C{input swipe} command.
        @param (x0, y0): starting point in PX
        @param (x1, y1): ending point in PX
        @param duration: duration of the event in ms
        @param steps: number of steps (currently ignored by @{input swipe})
        @param orientation: the orientation (-1: undefined)
        """
        if orientation == -1:
            orientation = self.getOrientation()
        (x0, y0) = self.__transformPointByOrientation((x0, y0), orientation, self.getOrientation())
        (x1, y1) = self.__transformPointByOrientation((x1, y1), orientation, self.getOrientation())

        version = self.getSDKVersion()
        if version <= 15:
            self.logger.error("drag: API <= 15 not supported (version=%d)" % version)
        elif version <= 17:
            self.shell("input swipe %d %d %d %d" % (x0, y0, x1, y1))
        else:
            self.shell("input touchscreen swipe %d %d %d %d %d" % (x0, y0, x1, y1, duration))

    def type(self, text):
        if isinstance(text, str):
            escaped = text.replace("%s", "\\%s")
            encoded = escaped.replace(" ", "%s")
        else:
            encoded = str(text)
        #FIXME find out which characters can be dangerous,
        # for exmaple not worst idea to escape "
        self.shell("input text %s" % encoded)
