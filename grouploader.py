# -*- coding: utf-8 -*-

#!/usr/bin/env python

import json
import os
import time
from datetime import datetime

import webapp2
import jinja2
import wowapi
import logging

from google.appengine.ext import ndb
from google.appengine.api import memcache
from passlib.hash import sha256_crypt

# Minimum ilvls and colors for the ilvl grid
MIN_NORMAL = 385
MIN_HEROIC = 400
MIN_MYTHIC = 415
COLOR_LFR = '#FFB2B2'
COLOR_NORMAL = '#FFFFB2'
COLOR_HEROIC = '#B2FFB2'
COLOR_MYTHIC = '#C3BEFF'
COLOR_LEGENDARY = '#FFCA68'

CLASS_INDEXES = {
    'Warrior': 1,
    'Paladin': 2,
    'Hunter': 3,
    'Rogue': 4,
    'Priest': 5,
    'Death Knight': 6,
    'Shaman': 7,
    'Mage': 8,
    'Warlock': 9,
    'Monk': 10,
    'Druid': 11,
    'Demon Hunter': 12
}

# This is used to color the table cells on the grid display based on the ilvl
# of the item.  It gets put into the jinja environment as a filter.
def ilvlcolor(ilvl, quality):
    retval = ''
    if quality == 5:
        retval = 'background-color:'+COLOR_LEGENDARY
    elif ilvl > 0 and ilvl < MIN_NORMAL:
        retval = 'background-color:'+COLOR_LFR
    elif ilvl >= MIN_NORMAL and ilvl < MIN_HEROIC:
        retval = 'background-color:'+COLOR_NORMAL
    elif ilvl >= MIN_HEROIC and ilvl < MIN_MYTHIC:
        retval = 'background-color:'+COLOR_HEROIC
    elif ilvl >= MIN_MYTHIC:
        retval = 'background-color:'+COLOR_MYTHIC
    return retval

def normalize(groupname):
    return groupname.lower().replace('\'', '').replace(' ', '-')

def build_wowhead_rel(item, player_class):

    rel_entries = []

    bonus_lists = item.get('bonusLists', [])
    if bonus_lists:
        rel_entries.append('bonus=%s' % ':'.join(map(str, bonus_lists)))

    tooltips = item.get('tooltips', {})
    if tooltips.get('enchant', ''):
        rel_entries.append('ench=%s' % tooltips['enchant'])

    if tooltips.get('gems', ''):
        rel_entries.append('gems=%s' % tooltips['gems'])

    if tooltips.get('set', ''):
        rel_entries.append('pcs=%s' % tooltips['set'])

    azerite_ids = item.get('azerite', [])
    if azerite_ids:
        powers = [CLASS_INDEXES[player_class]] + [x for x in azerite_ids if x != 0]
#        powers = [x for x in azerite_ids if x != 0]
        rel_entries.append('azerite-powers=%s' % ':'.join(map(str, powers)))

    return '&'.join(rel_entries)

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'])
JINJA_ENVIRONMENT.filters['ilvlcolor'] = ilvlcolor
JINJA_ENVIRONMENT.filters['normalize'] = normalize
JINJA_ENVIRONMENT.filters['build_wowhead_rel'] = build_wowhead_rel

class Toonv2(ndb.Model):
    name = ndb.StringProperty(indexed=True)
    role = ndb.StringProperty()
    main = ndb.BooleanProperty()
    realm = ndb.StringProperty()
    status = ndb.StringProperty()

class Groupv2(ndb.Model):
    nrealm = ndb.StringProperty(indexed=True)
    ngroup = ndb.StringProperty(indexed=True)
    groupname = ndb.StringProperty()
    password = ndb.StringProperty()
    toons = ndb.StructuredProperty(Toonv2, repeated=True)
    lastvisited = ndb.DateTimeProperty()

    @staticmethod
    def normalize(realm):
        return realm.lower().replace('\'', '').replace(' ', '-')

class GroupStats:

    # the number of mains that should be used to calculate the group average
    # ilvl and equipped ilvls.  this may be different from the total number of
    # mains since there may be errors retrieving data from Battle.net.
    ilvlmains = 0
    totalilvl = 0
    totalilvleq = 0

    cloth = 0
    leather = 0
    mail = 0
    plate = 0

    ranged = 0
    melee = 0

def get_group_from_db(nrealm, ngroup):

    results = memcache.get('%s_%s' % (nrealm, ngroup))
    if results is None:
        logging.info('group was not in memcache')
        db_query = Groupv2.query(Groupv2.nrealm == nrealm, Groupv2.ngroup == ngroup)
        queryresults = db_query.fetch(1)
        if queryresults:
            logging.info('found group in datastore, adding to memcache')
            results = queryresults[0]
            memcache.set('%s_%s' % (nrealm, ngroup), results)
        else:
            logging.info('group was not in datastore either')

    return results

class Editor(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        self.edit_group(nrealm, ngroup)

    def edit_group(self, nrealm, ngroup):

        # load the list of realms from the datastore that was loaded by the
        # /loadrealms service
        query = wowapi.Realm.query(namespace='Realms')
        realms = query.fetch()

        # try to load the group info from the database
        results = get_group_from_db(nrealm, ngroup)

        # Loop through the results from the data store and create a list
        # of toon names, the markers for subs, and the markers for
        # cross-realm.  If there weren't any results, blank lists will be
        # passed to the template.
        toons = []
        if results is not None:
            for toon in results.toons:
                newtoon = {
                    'name': toon.name,
                    'role': toon.role,
                    'status': toon.status,
                    'realm': str([x.realm for x in realms if x.slug == toon.realm][0])
                }

                toons.append(newtoon)

        # throw them at jinja to generate the actual html
        template_values = {
            'group': ngroup,
            'nrealm': nrealm,
            'realm': str([x.realm for x in realms if x.slug == nrealm][0]),
            'toons': toons,
            'realms': realms,
        }
        template = JINJA_ENVIRONMENT.get_template('templates/editor.html')
        self.response.write(template.render(template_values))

        template = JINJA_ENVIRONMENT.get_template('templates/pagefooter.html')
        self.response.write(template.render())

class GridLoader(webapp2.RequestHandler):
    def get(self, nrealm, ngroup):
        # try to load the group info from the database
        results = get_group_from_db(nrealm, ngroup)

        # if the group doesn't exist, drop into the interface to make a new
        # group
        if results is None:
            self.redirect('/edit/%s/%s' % (nrealm, ngroup))

        # if the group exists, load the group from the blizzard API and display
        # it.
        else:
            results.lastvisited = datetime.now()
            results.put()
            self.load_group(results)

    def post(self, nrealm, ngroup):

        # try to load the group info from the database.  this is only necessary
        # to get the password from the database to verify that it's correct.
        results = get_group_from_db(nrealm, ngroup)

        if results is not None and not sha256_crypt.verify(self.request.get('pw'), results.password):
            self.response.write('<html><head><title>Password failure</title></head>\n')
            self.response.write('<body>\n')
            self.response.write('Password did not match for this group!<p/>')
            self.response.write('<a href="javascript:history.back()">Go Back</a>\n')
            self.response.write('</body></html>')
            self.response.status = 401
            return

        group = None
        if results != None:
            group = results
        else:
            group = Groupv2()

        group.nrealm = nrealm
        group.ngroup = ngroup
        group.groupname = self.request.get('group').strip()

        group.password = sha256_crypt.encrypt(self.request.get('pw'))

        # load the json data that includes the toon data
        jsondata = json.loads(self.request.get('json').strip())
        logging.info('number of toons saved: %d', len(jsondata['toons']))

        # clear the old toon information and recreate it from the data from
        # the form
        del group.toons[:]
        for j in jsondata['toons']:
            toon = Toonv2()
            toon.name = j['name']
            toon.role = j['role']
            toon.status = j['status']
            toon.realm = j['realm']
            group.toons.append(toon)

        group.toons = sorted(group.toons, key=lambda s: s.name.lower())
        group.lastvisited = datetime.now()
        group.put()

        # put this group in the memcache too so that it can be loaded from
        # there instead of from the datastore every time
        memcache.set('%s_%s' % (nrealm, ngroup), group)

        # this is absolutely terrible, but sleep here for a second or two.
        # the reasoning is that the call from the editor page returns there
        # too quickly and will try to redirect to a page that doesn't exist
        # in the datastore yet.  that causes it to redirect back to the
        # editor page (see the get() function above).  sleeping here ensures
        # that the data was written before the redirection happens.
        results = []
        while not results:
            time.sleep(0.5)
            db_query = Groupv2.query(Groupv2.nrealm == nrealm, Groupv2.ngroup == ngroup)
            results = db_query.fetch(1)

    def load_group(self, results):

        # Get the group data from the results
        toonlist = results.toons
        realm = results.nrealm

        # Query ndb for the full realm name based on the results
        realm_query = wowapi.Realm.query(wowapi.Realm.slug == realm, namespace='Realms')
        realm_result = realm_query.fetch()
        frealm = realm_result[0].realm

        query = wowapi.ClassEntry.query()
        res = query.fetch()

        classes = {}
        for cls in res:
            classes[cls.classId] = cls.name

        data = []
        groupstats = GroupStats()

        # Use the API importer to load the data for the group into a list of
        # entries for each toon.  We'll loop through this data to build up
        # the page once all of the fetches are finished.
        importer = wowapi.Importer()
        importer.load(realm, frealm, toonlist, data, groupstats)

        # Catch the case where no mains were found in the data so we don't
        # divide by zero
        if groupstats.ilvlmains == 0:
            avgilvl = 0
            avgeqp = 0
        else:
            avgilvl = groupstats.totalilvl / groupstats.ilvlmains
            avgeqp = groupstats.totalilvleq / groupstats.ilvlmains

        melee = 0
        ranged = 0
        tanks = 0
        healers = 0
        for idx, char in enumerate(data):
            if char['status'] == 'main':
                if char['role'] == 'dps':
                    melee += 1
                elif char['role'] == 'ranged':
                    ranged += 1
                elif char['role'] == 'tank':
                    tanks += 1
                elif char['role'] == 'healer':
                    healers += 1

        # Build the page header with the group name, realm, and ilvl stats
        template_values = {
            'group': results.groupname,
            'frealm': frealm,
            'ngroup': results.ngroup,
            'nrealm': results.nrealm,
            'groupavgilvl': avgilvl,
            'groupavgeqp': avgeqp,
            'toondata': data,
            'tankcount': tanks,
            'healercount': healers,
            'meleecount': melee,
            'rangedcount': ranged,
            'clothcount': groupstats.cloth,
            'leathercount': groupstats.leather,
            'mailcount': groupstats.mail,
            'platecount': groupstats.plate,
        }
        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-header.html')
        self.response.write(template.render(template_values))

        self.response.write('        <hr style="width:90%;clear: both"/><br/>\n')

        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-gridheader.html')
        self.response.write(template.render(template_values))
        self.response.write('<tbody>\n')

        # Loop through the data twice here to display the separate sections,
        # but don't actually loop through all of the data.  The lambda filters
        # filter the character data down to just the parts that are needed
        # for each loop.
        for idx, char in enumerate(data):
            self.add_character(char, results, classes)

        self.response.write('</table><p/>\n')
        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-colorlegend.html')
        template_values = {
            'min_normal': MIN_NORMAL,
            'min_heroic': MIN_HEROIC,
            'min_mythic': MIN_MYTHIC,
            'color_lfr': COLOR_LFR,
            'color_normal': COLOR_NORMAL,
            'color_heroic': COLOR_HEROIC,
            'color_mythic': COLOR_MYTHIC,
        }
        self.response.write(template.render(template_values))

        template = JINJA_ENVIRONMENT.get_template('templates/pagefooter.html')
        self.response.write(template.render())

    # Generic method to add a character to the page response
    def add_character(self, char, results, classes):

        if 'load_status' in char and char['load_status'] == 'nok':
            template_values = {
                'name': char['name'],
                'load_status': char['load_status'],
                'reason': char['reason'],
                'realm': char['toonrealm'],
                'frealm': char['toonfrealm'],
            }
        elif 'items' in char:

            itemslots = ['head', 'shoulder', 'chest', 'hands', 'legs', 'feet', 'neck',
                         'back', 'wrist', 'waist', 'finger1', 'finger2', 'trinket1',
                         'trinket2', 'mainHand', 'offHand']
            items = char['items']

            avgilvleq = 0
            numitems = 0
            for slot in itemslots:
                if slot in items:
                    avgilvleq = avgilvleq + items[slot]['itemLevel']
                    numitems = numitems + 1
            # if there's no offhand, assume the main hand is a 2-hander and count it double per Blizzard iLvl formula.
            if (not 'offHand' in items) and ('mainHand' in items):
                avgilvleq = avgilvleq + items['mainHand']['itemLevel']
                numitems = numitems + 1

            if numitems != 0:
                avgilvleq = round(float(avgilvleq)/float(numitems), 1)

            template_values = {
                'load_status': 'ok',
                'name': char['name'],
                'frealm': char['toonfrealm'],   # full realm name
                'nrealm': results.nrealm,  # realm for group
                'realm': char['toonrealm'],  # realm for toon (might not be == to nrealm)
                'guild': char['guild']['name'] if 'guild' in char else None,
                'class': classes[char['class']],
                'status': char['status'],
                'role': char['role'],
                'avgilvl': items['averageItemLevel'],
                'avgilvle': avgilvleq,
                'azeriteLevel': items.get('neck', {}).get('azeriteLevel', 0)
            }

            for itype in itemslots:
                template_values[itype] = {}
                if itype in items:
                    azerite_ids = []
                    if 'azeriteEmpoweredItem' in items[itype]:
                        for power in items[itype]['azeriteEmpoweredItem'].get('azeritePowers', []):
                            azerite_ids.append(power['id'])

                    template_values[itype]['id'] = items[itype]['id']
                    template_values[itype]['enchant'] = items[itype]['enchant']
                    template_values[itype]['itemLevel'] = items[itype]['itemLevel']
                    template_values[itype]['bonusLists'] = items[itype]['bonusLists']
                    template_values[itype]['tooltips'] = items[itype]['tooltipParams']
                    template_values[itype]['quality'] = items[itype]['quality']
                    template_values[itype]['azerite'] = azerite_ids
                    if items[itype]['context'] == 'trade-skill':
                        template_values[itype]['set'] = 'crafted'
                    else:
                        template_values[itype]['set'] = 'no'
                else:
                    template_values[itype]['itemLevel'] = 0
                    template_values[itype]['set'] = False

        else:

            template_values = {
                'name': char['name'],
                'load_status': 'nok',
                'reason': 'Unknown error retrieving data for %s.  Refresh to try again' % char['name'],
                'realm': char['toonrealm'],
                'frealm': char['toonfrealm'],
            }

        template = JINJA_ENVIRONMENT.get_template('templates/groupinfo-gridtoon.html')
        self.response.write(template.render(template_values))

class Validator(webapp2.RequestHandler):
    def post(self):
        ngroup = self.request.get('group')
        nrealm = self.request.get('realm')
        password = self.request.get('pw')
        newgn = self.request.get('newgn')

        if password != None:
            # check that the realm and group names are valid, as a safety
            # measure.
            if (nrealm is None or ngroup is None):
                self.response.status = 401
                self.response.write('Invalid')
                return

            # grab the group the datastore and try to validate the password
            results = get_group_from_db(nrealm, ngroup)

            if results != None:
                if not sha256_crypt.verify(password, results.password):
                    self.response.status = 401
                    self.response.write('Invalid')
                else:
                    self.response.status = 200
                    self.response.write('Valid')
            else:
                # This covers the case where a group is being added since
                # it won't be in the database yet.
                self.response.status = 200
                self.response.write('Valid')
        elif newgn != None:
            results = get_group_from_db(nrealm, ngroup)

            if results != None:
                self.response.status = 401
                self.response.write('Invalid')
            else:
                self.response.status = 200
                self.response.write('Valid')

class StatusMigration(webapp2.RequestHandler):
    def get(self):
        groups = Groupv2.query().fetch()
        for group in groups:
            for toon in group.toons:
                if toon.main:
                    toon.status = 'main'
                else:
                    toon.status = 'bench'

            group.put()
