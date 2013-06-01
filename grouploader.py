# -*- coding: utf-8 -*-

#!/usr/bin/env python

import webapp2
import json,math,sys,pprint
from google.appengine.ext import ndb
from google.appengine.api.memcache import Client
from google.appengine.api import urlfetch
from passlib.hash import sha256_crypt

class Group(ndb.Model):
    nrealm = ndb.StringProperty(indexed=True)
    ngroup = ndb.StringProperty(indexed=True)
    groupname = ndb.StringProperty()
    toons = ndb.StringProperty(repeated=True)
    password = ndb.StringProperty()

    @staticmethod
    def normalize(realm):
        return realm.lower().replace('\'','').replace(' ','-')

class Realm(ndb.Model):
    realm = ndb.StringProperty(indexed=True,required=True)
    slug = ndb.StringProperty(indexed=True,required=True)

class Loader(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        
        # try to load the group info from the database
        db_query = Group.query(Group.nrealm==nrealm, Group.ngroup==ngroup)
        results = db_query.fetch(5)
        
        # if the group doesn't exist, drop into the interface to make a new
        # group
        if (len(results) == 0):
            self.redirect('/edit/%s/%s' % (nrealm, ngroup))
        
        # if the group exists, load the group from the blizzard API and
        # display it.
        # if the group doesn't exist, show the page to create a new
        # group.
        else:
            self.loadGroup(results[0])

    def post(self, nrealm, ngroup):
        
        # try to load the group info from the database
        db_query = Group.query(Group.nrealm==nrealm, Group.ngroup==ngroup)
        results = db_query.fetch(5)
        
        if ((len(results) != 0) and
            sha256_crypt.verify(self.request.get('pw'), results[0].password) != True):
            self.response.write('Password did not match for this group!')
            return
        
        group = None
        if (len(results) != 0):
            group = results[0]
        else:
            group = Group()
        
        group.nrealm = nrealm
        group.ngroup = ngroup
        group.groupname = self.request.get('group').strip()
        group.password = sha256_crypt.encrypt(self.request.get('pw'))
        toons = self.request.POST.getall('toons')
        print 'number of toons saved: %d' % len(toons)
        group.toons = sorted(self.request.POST.getall('toons'), key=unicode.lower)
        group.put()

        self.loadGroup(group)

    def loadGroup(self, results):

        # Get the group data from the results
        toons = results.toons
        realm = results.nrealm
        
        # Query ndb for the full realm name based on the results
        rq = Realm.query(Realm.slug == realm, namespace='Realms')
        rqres = rq.fetch()
        frealm = rqres[0].realm

        self.response.write('<!DOCTYPE html>\n')
        self.response.write('<html>\n')
        self.response.write('<head>\n')
        self.response.write('<title>%s - %s</title>' %
                            (results.groupname, frealm))
        self.response.write('<link rel="stylesheet" type="text/css" href="/resources/raidgroup.css"/>\n')
        self.response.write('<script language="javascript" type="text/javascript" src="/resources/folder.js"></script>\n')
        self.response.write('<script language="javascript" type="text/javascript" src="/resources/creategroup.js"></script>\n')
        self.response.write('</head>\n')
        self.response.write('<body>\n')
        
        jsondata = dict()
        
        totalilvl = 0
        totalilvleq = 0
        
        for i in range(len(toons)):
            url = 'http://us.battle.net/api/wow/character/%s/%s?fields=items,guild,professions,progression' % (realm, toons[i]);
            response = urlfetch.fetch(url)
            jsondata[i] = json.loads(response.content)
            
            if 'status' in jsondata[i] and jsondata[i]['status'] == 'nok':
                print('Failed to find toon %s' % toons[i])
                jsondata[i]['toon'] = toons[i]
            else:
                totalilvl = totalilvl + jsondata[i]['items']['averageItemLevel'];
                totalilvleq = totalilvleq + jsondata[i]['items']['averageItemLevelEquipped']
        self.response.write('<div class="header">\n')
        self.response.write('<div style="float:left">\n')
        self.response.write('<div style="font-size: 24px">%s</div>\n' % results.groupname)
        self.response.write('<div style="font-size: 20px">%s - US</div>\n' % frealm)
        self.response.write('</div>\n')
        self.response.write('<div style="float:right">\n')
        self.response.write('<form action="/edit/%s/%s">' %
                            (results.nrealm, results.ngroup))
        self.response.write('<input type="submit" value="Edit Group">\n')
        self.response.write('</form>')
        self.response.write('</div>\n')
        self.response.write('</div>\n')
        self.response.write('</div>\n')
        self.response.write('Group Average ilvl: %d<br/>\n' % (totalilvl / len(toons)))
        self.response.write('Group Average equipped: %d<br/><br/>\n' % (totalilvleq / len(toons)))
        
        halfgroup = math.ceil(len(jsondata) / 2.0)
        self.response.write('<div class="left">\n')
        
        for u in range(len(jsondata)):
            
            char = jsondata[u]
            
            if (u == halfgroup):
                self.response.write('</div>')
                self.response.write('<div class="right">\n')
            
            if 'status' in char and char['status'] == 'nok':
                self.response.write('Failed to find toon %s (name change? server transfer?)<br/>\n' % char['toon'])
                continue
            
            self.response.write('<a href="http://us.battle.net/wow/en/character/%s/%s/simple">%s</a><br/>\n' % (realm.encode('utf-8'), char['name'].encode('utf-8'),char['name'].encode('utf-8')))
            
            self.response.write('<div style="margin-left:30px">\n')
            self.response.write('%s<br/>\n' % char['guild']['name'])
            self.response.write('Average ilvl: %d<br/>\n' % char['items']['averageItemLevel'])
            self.response.write('Average equipped: %d<br/>\n' % char['items']['averageItemLevelEquipped'])
            
            priprof = char['professions']['primary']
            
            if (len(priprof) == 2):
                self.response.write('Profession #1: %s (%d)<br/>\n' % (priprof[0]['name'], priprof[0]['rank']))
                self.response.write('Profession #2: %s (%d)<br/>\n' % (priprof[1]['name'], priprof[1]['rank']))
            elif (len(priprof) == 1):
                self.response.write('Profession #1: %s (%d)<br/>\n' % (priprof[0]['name'], priprof[0]['rank']))
                self.response.write('Profession #2: none<br/>\n')
            else:
                self.response.write('Profession #1: none<br/>\n')
                self.response.write('Profession #2: none<br/>\n')
            
            self.response.write('<div>\n')
            self.response.write('<div onclick="togglePanelStatus(\'%s\')" style="cursor: pointer">\n' % char['name'])
            self.response.write('<img src="/resources/arrow_right.png" id="slotsimg%s">' % char['name'])
            self.response.write('Gear Slot ilvls\n')
            self.response.write('</div>\n')
            self.response.write('<div id="slots%s" style="display: none;margin-left: 16px">\n' % char['name'])
            self.response.write('<div class="left">\n')
            self.response.write('Head: %d<br/>\n' % char['items']['head']['itemLevel'])
            self.response.write('Neck: %d<br/>\n' % char['items']['neck']['itemLevel'])
            self.response.write('Shoulder: %d<br/>\n' % char['items']['shoulder']['itemLevel'])
            self.response.write('Back: %d<br/>\n' % char['items']['back']['itemLevel'])
            self.response.write('Chest: %d<br/>\n' % char['items']['chest']['itemLevel'])
            self.response.write('Wrist: %d<br/>\n' % char['items']['wrist']['itemLevel'])
            self.response.write('Hands: %d<br/>\n' % char['items']['hands']['itemLevel'])
            self.response.write('Waist: %d<br/>\n' % char['items']['waist']['itemLevel'])
            self.response.write('</div>')
            self.response.write('<div class="left">\n')
            self.response.write('Legs: %d<br/>\n' % char['items']['legs']['itemLevel'])
            self.response.write('Feet: %d<br/>\n' % char['items']['feet']['itemLevel'])
            self.response.write('Ring 1: %d<br/>\n' % char['items']['finger1']['itemLevel'])
            self.response.write('Ring 2: %d<br/>\n' % char['items']['finger2']['itemLevel'])
            self.response.write('Trinket 1: %d<br/>\n' % char['items']['trinket1']['itemLevel'])
            self.response.write('Trinket 2: %d<br/>\n' % char['items']['trinket2']['itemLevel'])
            self.response.write('Main Hand: %d<br/>\n' % char['items']['mainHand']['itemLevel'])
            if ('offHand' in char['items']):
                self.response.write('Off Hand: %d<br/>\n' % char['items']['offHand']['itemLevel'])
            else:
                self.response.write('Off Hand: none<br/>\n')
            self.response.write('</div>\n')
            self.response.write('</div><br/>\n')
            self.response.write('</div>\n')
            self.response.write('</div>\n')
        
        self.response.write('</div><p/>\n');
        self.response.write('</body>\n</html>')

class Editor(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        self.editGroup(nrealm, ngroup)
    
    def editGroup(self, nrealm, ngroup):
        
        # try to load the group info from the database
        db_query = Group.query(Group.nrealm==nrealm, Group.ngroup==ngroup)
        queryresults = db_query.fetch(5)
        
        results = None
        if (len(queryresults) != 0):
            results = queryresults[0]
        
        self.response.write('<!DOCTYPE html>\n')
        self.response.write('<html>\n')
        self.response.write('<head>\n')
        
        title = "Editing Group"
        if (results == None):
            title = "Creating New Group"
        
        self.response.write('<title>%s</title>\n' % title)
        self.response.write('<script language="javascript" type="text/javascript" src="/resources/creategroup.js"></script>')
        self.response.write('</head>\n\n')
        self.response.write('<body>\n')
        self.response.write('<h1>%s</h1>\n' % title)
        
        self.response.write('<form action="/%s/%s" method="post" autocomplete="off" onsubmit="selectAllToons();">\n' % (nrealm, ngroup))
        if (results == None):
            self.response.write('Group name: <input type="text" name="group" id="group"><p/>\n')
        else:
            self.response.write('Group name: <input type="text" name="group" id="group"value="%s"><p/>\n' % results.groupname)
        
        self.response.write('Group members:<br>\n')
        self.response.write('<select size="10" multiple="multiple" style="width: 300px" name="toons" id="toons">\n')
        
        if (results != None):
            for toon in results.toons:
                self.response.write('<option id="opt%s">%s\n' % (toon,toon))
        
        self.response.write('</select><br>\n')
        self.response.write('Add Toon: <input type="text" name="newtoon" id="newtoon"><br>\n')
        self.response.write('<input type="button" onclick="addToList()" value="Add">')
        self.response.write('<input type="button" onclick="removeFromList()" value="Remove" id="removebutton"><p/>\n')
        if (results == None):
            self.response.write('Enter a password to enable editing the group later:<br>\n')
        else:
            self.response.write('Enter password to save group:<br>\n')
        self.response.write('Password:')
        self.response.write('<input type="password" name="pw"><p/>\n')
        self.response.write('<input type="submit" value="Save">\n')
        self.response.write('</form>\n')
        self.response.write('</body>\n')
        self.response.write('</html>')