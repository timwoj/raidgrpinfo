# -*- coding: utf-8 -*-

#!/usr/bin/env python

import webapp2
import json,math,sys,pprint,os
import jinja2
from google.appengine.ext import ndb
from google.appengine.api.memcache import Client
from google.appengine.api import urlfetch
from passlib.hash import sha256_crypt


JINJA_ENVIRONMENT = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
                                       extensions=['jinja2.ext.autoescape'])

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
        print 'Loader.get'
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
        
        print 'Loader.post'
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
        
        # TODO: move this stuff to be part of the realm loader since it shouldn't change
        # very often
        response = urlfetch.fetch('http://us.battle.net/api/wow/data/character/classes')
        rawclasses = json.loads(response.content)
        sortedclasses = sorted(rawclasses['classes'], key=lambda k: k['id'])
        
        classes = dict()
        for c in sortedclasses:
            classes[c['id']] = c['name']

        jsondata = dict()
        
        totalilvl = 0
        totalilvleq = 0
        
        clothcount = 0
        leathercount = 0
        mailcount = 0
        platecount = 0
        
        # rogue/mage/druid/dk tokens
        vanqcount = 0
        # paladin/priest/warlock tokens
        conqcount = 0
        # warrior/hunter/shaman/monk tokens
        protcount = 0
        
        for i in range(len(toons)):
            url = 'http://us.battle.net/api/wow/character/%s/%s?fields=items,guild,professions,progression' % (realm, toons[i]);
            response = urlfetch.fetch(url)
            jsondata[i] = json.loads(response.content)
            
            if 'status' in jsondata[i] and jsondata[i]['status'] == 'nok':
                print('Failed to find toon %s' % toons[i].encode('utf-8'))
                jsondata[i]['toon'] = toons[i]
            else:
                totalilvl = totalilvl + jsondata[i]['items']['averageItemLevel'];
                totalilvleq = totalilvleq + jsondata[i]['items']['averageItemLevelEquipped']
                
                toonclass = classes[jsondata[i]['class']]
                if toonclass in ['Paladin','Warrior','Death Knight']:
                    platecount += 1
                elif toonclass in ['Mage','Priest','Warlock']:
                    clothcount += 1
                elif toonclass in ['Druid','Monk','Rogue']:
                    leathercount += 1
                elif toonclass in ['Hunter','Shaman']:
                    mailcount += 1
                
                if toonclass in ['Paladin','Priest','Warlock']:
                    conqcount += 1
                elif toonclass in ['Warrior','Hunter','Shaman','Monk']:
                    protcount += 1
                elif toonclass in ['Death Knight','Druid','Mage','Rogue']:
                    vanqcount += 1

        halfindex = math.ceil(len(jsondata) / 2.0)

        # throw them at jinja to generate the actual html
        template_values = {
            'group' : results.groupname,
            'frealm' : frealm,
            'ngroup' : results.ngroup,
            'nrealm' : results.nrealm,
            'groupavgilvl' : totalilvl / len(toons),
            'groupavgeqp' : totalilvleq / len(toons),
        }
        template = JINJA_ENVIRONMENT.get_template('groupinfo-header.html')
        self.response.write(template.render(template_values))
        
        self.response.write('        <hr style="width:90%"/><br/>\n')

        template_values = {
            'clothcount' : clothcount,
            'leathercount' : leathercount,
            'mailcount' : mailcount,
            'platecount' : platecount,
            'conqcount' : conqcount,
            'protcount' : protcount,
            'vanqcount' : vanqcount,
        }
        template = JINJA_ENVIRONMENT.get_template('groupinfo-armortokens.html')
        self.response.write(template.render(template_values))

        self.response.write('        <hr style="width:90%"/><br/>\n')

        self.response.write('        <div style="font-size: 20px">Characters in Group</div>\n')
        self.response.write('        <br/>\n')
        self.response.write('        <div class="left">\n')

        for u in range(len(jsondata)):
                    
            char = jsondata[u]
                    
            if (u == halfindex):
                self.response.write('        </div>')
                self.response.write('        <div class="right">\n')
            
            if 'status' in char and char['status'] == 'nok':
                template_values = {
                    'name' : char['toon'],
                    'avgilvl' : 0
                }
            else:
        
                items = char['items']
                template_values = {
                    'name' : char['name'],
                    'realm' : results.nrealm,
                    'guild' : char['guild']['name'],
                    'class' : classes[char['class']],
                    'avgilvl' : char['items']['averageItemLevel'],
                    'avgilvle' : char['items']['averageItemLevelEquipped'],
                    'head' : items['head']['itemLevel'] if 'head' in items else None,
                    'neck' : items['neck']['itemLevel'] if 'neck' in items else None,
                    'shoulder' : items['shoulder']['itemLevel'] if 'shoulder' in items else None,
                    'back' : items['back']['itemLevel'] if 'back' in items else None,
                    'chest' : items['chest']['itemLevel'] if 'chest' in items else None,
                    'wrist' : items['wrist']['itemLevel'] if 'wrist' in items else None,
                    'hands' : items['hands']['itemLevel'] if 'hands' in items else None,
                    'waist' : items['waist']['itemLevel'] if 'waist' in items else None,
                    'legs' : items['legs']['itemLevel'] if 'legs' in items else None,
                    'feet' : items['feet']['itemLevel'] if 'feet' in items else None,
                    'finger1' : items['finger1']['itemLevel'] if 'finger1' in items else None,
                    'finger2' : items['finger2']['itemLevel'] if 'finger2' in items else None,
                    'trinket1' : items['trinket1']['itemLevel'] if 'trinket1' in items else None,
                    'trinket2' : items['trinket2']['itemLevel'] if 'trinket2' in items else None,
                    'mainHand' : items['mainHand']['itemLevel'] if 'mainHand' in items else None,
                    'offHand' : items['offHand']['itemLevel'] if 'offHand' in items else None,
                }

                priprof = char['professions']['primary']
                if (len(priprof) == 2):
                    template_values['prof1'] = priprof[0]['name']
                    template_values['prof1skill'] = priprof[0]['rank']
                    template_values['prof2'] = priprof[1]['name']
                    template_values['prof2skill'] = priprof[1]['rank']
                elif (len(priprof) == 1):
                    template_values['prof1'] = priprof[0]['name']
                    template_values['prof1skill'] = priprof[0]['rank']
                    template_values['prof2'] = None
                else:
                    template_values['prof1'] = None
                    template_values['prof2'] = None

            template = JINJA_ENVIRONMENT.get_template('groupinfo-toon.html')
            self.response.write(template.render(template_values))

        self.response.write('       </div>\n');
        self.response.write('    </body>\n');
        self.response.write('</html>')

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
        
        # throw them at jinja to generate the actual html
        template_values = {
            'group' : ngroup,
            'realm' : nrealm,
            'results' : results,
        }
        template = JINJA_ENVIRONMENT.get_template('editor.html')
        self.response.write(template.render(template_values))
