#!/usr/bin/env python3
# Copyright 2015 Joren Van Onder
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import urllib.request
import urllib.parse
import urllib.error
import sys
import json
import pprint
import argparse
import subprocess
import os.path
import threading
import queue

userAgent = "jorenvo.reddit-to-m3u.py"

class DomainChecker:
    """Used to check for approved domains"""
    approvedDomainsYoutube = ["youtube.com", "youtu.be"]
    approvedDomainsOther = ["soundcloud.com", "bandcamp.com"]

    def __init__(self, domainToCheck):
        self.domainToCheck = domainToCheck

    def __domainInApprovedList(self, domainList):
        for domain in domainList:
            if domain in self.domainToCheck:
                return(True)

        return(False)

    def isApproved(self):
        if self.__domainInApprovedList(self.approvedDomainsYoutube) or self.__domainInApprovedList(self.approvedDomainsOther):
            return(True)
        else:
            return(False)

    def isYoutube(self):
        return(self.__domainInApprovedList(self.approvedDomainsYoutube))

def parseArguments():
    parser = argparse.ArgumentParser(description = "Creates an Extended M3U playlist based on (a) subreddit(s).")
    parser.add_argument("-o", "--output-file", help = "path where the m3u playlist should be saved (default: %(default)s)", default = "~/.mpd/playlists/reddit.m3u")
    parser.add_argument("-l", "--limit",
                        help = "maximum amount of tracks that need to be requested from reddit.com (reddit api max: 100) (default: %(default)s)",
                        type = int, default = 20)
    parser.add_argument("-n", "--amount-of-threads",
                        help = "amount of youtube-dl threads that will be spawned (default: %(default)s)",
                        type = int, default = 16)
    parser.add_argument("subreddit", help = "one or more subreddits (eg: futuresynth+electronicjazz)")
    parser.add_argument("sort", choices = ["hot", "hour", "day", "week", "month", "year", "all"], help = "sorting method")

    args = parser.parse_args()
    return(args)

def prettyPrint(obj):
    pp = pprint.PrettyPrinter(indent = 4)
    pp.pprint(obj)

def writeStringToFile(filename, string):
    f = open(filename, 'w')
    print(string, end="", file=f)
    f.close()

def unescape(s):
    s = s.replace("&lt;", "<")
    s = s.replace("&gt;", ">")
    # this has to be last:
    s = s.replace("&amp;", "&")
    return(s)

def createListOfTracks(subreddit, sort, limit):
    # https://www.reddit.com/dev/api#GET_{sort}
    url = "https://www.reddit.com/r/" + subreddit

    if sort == "hot":
        url += "/hot.json?"
    else:
        url += "/top.json?t=" + sort + "&"

    url += "limit=" + str(limit)

    headers = {"User-Agent" : userAgent}

    req = urllib.request.Request(url, None, headers)
    response = urllib.request.urlopen(req).read().decode("utf-8")

    # writeStringToFile("test.json", response)
    # response = open("test.json", "r").read()

    response = json.loads(response)
    response = response["data"]["children"]

    trackList = []

    for link in response:
        link = link["data"]

        domainChecker = DomainChecker(link["url"])
        if domainChecker.isApproved():
            trackList.append({"domain": link["domain"],
                              "title": link["title"],
                              "url": unescape(link["url"])})

    return(trackList)

def getUrlWithYoutubeDl(url, domain, title):
    domainChecker = DomainChecker(domain)
    rawUrl = ""
    command = ["youtube-dl", "--no-playlist", "-g"]

    try:
        if domainChecker.isYoutube():
            rawUrl = subprocess.check_output(command + ["-f", "bestaudio", url]).decode("utf-8").rstrip("\n")
        else:
            rawUrl = subprocess.check_output(command + [url]).decode("utf-8").rstrip("\n")
    except subprocess.CalledProcessError:
        print("ERROR: " + title + " (" + url + ")")
        rawUrl = ""

    return(rawUrl)

def getRawUrlThread(trackQueue):
    while True:
        link = trackQueue.get()
        print(link["title"] + ": " + link["url"])

        rawUrl = getUrlWithYoutubeDl(link["url"], link["domain"], link["title"])

        if not "\n" in rawUrl:
            link["rawUrl"] = rawUrl
        else:
            link["rawUrl"] = ""

        trackQueue.task_done()

def getRawUrls(trackList, amountOfWorkerThreads):
    lock = threading.Lock()
    trackQueue = queue.Queue()

    # init and start the worker threads
    for i in range(amountOfWorkerThreads):
        t = threading.Thread(target = getRawUrlThread, args = (trackQueue,))
        t.daemon = True
        t.start()

    # give the worker threads work
    for track in trackList:
        trackQueue.put(track)

    # wait until all the work in the queue is done
    trackQueue.join()

def writeTrackList(filename, trackList):
    f = open(filename, "w")
    print("#EXTM3U", file = f)

    for track in trackList:
        rawUrl = track["rawUrl"]

        if rawUrl:
            print("#EXTINF:-1," + track["title"], file = f)
            print(rawUrl, file = f)

    f.close()

arguments = parseArguments()
trackList = createListOfTracks(arguments.subreddit, arguments.sort, arguments.limit)

getRawUrls(trackList, arguments.amount_of_threads)

writeTrackList(os.path.expanduser(arguments.output_file), trackList)
