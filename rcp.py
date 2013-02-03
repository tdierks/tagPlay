#!/usr/bin/python

import sys
import socket
import re

TIMEOUT = 10.0
DEBUG = False

RESULT_CODES = set("""OK GenericError
  ErrorDisconnected ResourceAllocationError Disconnected ParameterError
  ErrorInitialSetupRequired ErrorAlreadySubscribed ErrorNotSubscribed
  ErrorUnsupported, Complete, NotComplete""".split())

class CommandError(Exception):
  def __init__(self, message, command, args, response):
    super(CommandError, self).__init__("%s for %s %s: %s" %
      (message, command, " ".join(args), response))

class Track(object):
  server = None
  artist = None
  album = None
  track = None
  
  def __init__(self, server, artist, album, track):
    self.server = server
    self.artist = artist
    self.album = album
    self.track = track

class SoundBridge(object):
  __conn = None
  
  def __init__(self):
    pass
  
  # todo: possible exceptions: failure to connect, timeout or error on readline
  def connect(self, hostname, port=5555):
    sock = socket.create_connection((hostname, port), TIMEOUT)
    sock.settimeout(TIMEOUT)
    self.__conn = sock.makefile()
    sock.close()
    hello = self.__conn.readline().rstrip('\r\n')
    if hello != "roku: ready":
      raise Exception("Got unexpected Roku prompt on connect: %s" % hello)
  
  def readResponse(self, command):
    resp = self.__conn.readline().rstrip('\r\n')
    if DEBUG:
      print >>sys.stderr, "<<",resp
    return self.parseResponse(command, resp)
  
  def parseResponse(self, command, resp):
    m = re.match(r"%s: (.+)" % command, resp)
    if not m:
      raise CommandError("Bad response", command, [], resp)
    return m.group(1)
  
  def isListResponse(self, resp):
    m = re.match(r"ListResultSize (\d+)", resp)
    if not m:
      return False
    return int(m.group(1))

  def sendCommand(self, command, args):
    if DEBUG:
      print >>sys.stderr, ">>", command, " ", " ".join([str(a) for a in args])
    print >>self.__conn, command, " ", " ".join([str(a) for a in args])
    self.__conn.flush()

  def readListResponse(self, command, count):
    results = []
    for i in xrange(count):
      resp = self.readResponse(command)
      results.append(resp)
    resp = self.readResponse(command)
    if resp != 'ListResultEnd':
      raise CommandError("Expected ListResultEnd at end of list response", command, [], resp)
    return results

  def doMultiCommand(self, command, *args):
    self.sendCommand(command, args)
    results = []
    while True:
      resp = self.readResponse(command)
      if resp in RESULT_CODES:
        return (resp, results)
      results.append(resp)
  
  def readTransactionResponse(self, command, *args):
    result = self.readResponse(command)
    count = self.isListResponse(result)
    if count:
      result = self.readListResponse(command, count)
    resp = self.readResponse(command)
    if resp != 'TransactionComplete':
      raise CommandError("Expected TransactionComplete", command, args, resp)
    return result
  
  def doCommand(self, command, *args):
    self.sendCommand(command, args)
    resp = self.readResponse(command)
    if resp == 'TransactionInitiated':
      return self.readTransactionResponse(command)
    count = self.isListResponse(resp)
    if count:
      return self.readListResponse(command, count)
    return resp

  def getActiveServer(self):
    self.getConnectedServer() # sync current server with session active server
    (status, info) = self.doMultiCommand('GetActiveServerInfo')
    if status == 'OK':
      type = self.parseResponse('Type', info[0])
      name = self.parseResponse('Name', info[1])
      return (type, name)
    elif status == 'ErrorDisconnected':
      return None
    else:
      raise Error("Got status %s from GetActiveServerInfo" % status)
    # See note p109 about disconnected active servers
  
  def listServers(self):
    return self.doCommand('ListServers')
  
  def getConnectedServer(self):
    return self.doCommand('GetConnectedServer') == 'OK'
  
  def serverDisconnect(self):
    return self.doCommand("ServerDisconnect")
  
  def serverConnect(self, i):
    return self.doCommand('ServerConnect', str(i))
  
  def connectToServer(self, server):
    cur = self.getActiveServer()
    if cur and cur[1] == server:
      return
    else:
      servers = self.listServers()
      try:
        i = servers.index(server)
      except ValueError:
        raise Error("Server %s not found in available servers (%s)" % (server, ", ".join(servers)))
      status = self.serverDisconnect()
      if status not in ('ErrorDisconnected', 'Disconnected'):
        raise Error("Got status %s from ServerDisconnect" % status)
      status = self.serverConnect(i)
      if status != "Connected":
        raise Error("Got status %s from ServerConnect" % status)
  
  def setBrowseFilterArtist(self, artist):
    return self.doCommand('SetBrowseFilterArtist', artist)
  
  def setBrowseFilterAlbum(self, album):
    return self.doCommand('SetBrowseFilterAlbum', album)
  
  def listSongs(self):
    return self.doCommand('ListSongs')
  
  def matchingSongs(self, album=None, artist=None, server=None):
    if server:
      connectToServer(server)
    if artist:
      self.setBrowseFilterArtist(artist)
    if album:
      self.setBrowseFilterAlbum(album)
    return self.listSongs()

  def singleSong(self, song, album=None, artist=None, server=None):
    songs = self.matchingSongs(album, artist, server)
    try:
      return songs.index(song)
    except ValueError:
      raise Error("Song %s not found" % song)
  
  def queueAndPlay(self, i = 0):
    self.doCommand('QueueAndPlay', i)
  
  def listPresets(self):
    return self.doCommand('ListPresets')
  
  def playPreset(self, preset):
    return self.doCommand('PlayPreset', preset)
  
  def stop(self):
    return self.doCommand('Stop')
    
if __name__ == "__main__":
  c = SoundBridge()
  c.connect("172.16.0.54")
  print "Connected to: ", c.getActiveServer()
  c.connectToServer("iMac iTunes")
  c.queueAndPlay(c.singleSong("Purple People Eater", "Dr. Demento 20th Anniversary Collection - The Greatest Novelty Records Of All Time Disc 2", "Sheb Wooley"))
  