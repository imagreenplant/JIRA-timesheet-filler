from __future__ import division
from jira import JIRA
import datetime
import time
import workdays
import dateutil.parser
import logging
import sys



#############################################################################
# Fill out this section
username = ''   # Jira /LDAP username
password = ''   # Jira / LDAP password

# Choose a duration of time to automatically log your work.  At this time,
#  1 week or lower is recommended.
# The begin date
begin_year = 2016
begin_month = 4
begin_day = 11
# The end date
end_year = 2016
end_month = 4
end_day = 15

server = ''   # Place company Jira server here
#############################################################################


# Despite issues that are returned from queries, I (you) only want time allocated to tickets from 
# projects with these keys
compatible_projects_keys = ('','')  #Place applicable Project KEY names here

# BS I had to do to get a proper timezone to match JIRA's api's needs
class nyctz(datetime.tzinfo):
    def tzname(self):
        return "UTC"
    def utcoffset(self, dt):
        return datetime.timedelta(0)
    def dst(self, dt):
        return datetime.timedelta(0)

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
bdate = datetime.datetime(begin_year,begin_month,begin_day,12,12,12).replace(tzinfo=nyctz())
edate = datetime.datetime(end_year,end_month,end_day,12,12,12).replace(tzinfo=nyctz())

begin_date = bdate
end_date = edate

class WorklogFiller():
	"""Fills out your worklog for the given date range for you"""
	def __init__(self):
		self.jira = False
		self.begin_date = begin_date
		self.end_date = end_date
		self.active_ticket_list = []
		self.loginToJira()
		self.current_worklog = []
		self.projects_to_cache = ('')
		self.cached_worklogs = {}


		def __init__(self,*args,**kwargs):
			ValueError.__init__(self,*args,**kwargs)

	def loginToJira(self):
		if username and password:
			self.jira = JIRA(server,basic_auth=(username,password))

	def convertISO8601DateToDateTime(self,isotime):
		return dateutil.parser.parse(isotime)

	def convertToJQLDate(self,dttime):
		return dttime.strftime('"%Y/%m/%d"')

	def convertSeconds(self,time_in_seconds):
		return float(time_in_seconds)/60.0/60.0

	def convertSecondsToMinutes(self,time_in_seconds):
		return float(time_in_seconds)/60.0

	def convertWorkTime(self,seconds):
		return "".join([ str("%.0f" % self.convertSecondsToMinutes(seconds)),'m'])

	def getWorkDayRange(self, begin=begin_date,end=end_date):
		time_delta = end - begin
		workdays = [begin + datetime.timedelta(days=x) for x in range(0,time_delta.days) ]
		workdays = [ workday for workday in workdays if workday.weekday() < 5]

		logging.debug("Dates: %s" % workdays)
		return workdays


	def getWorklog(self, issue):
		if issue.fields.project.key in self.projects_to_cache:
			if issue.key in self.cached_worklogs.keys():
				logging.debug("Found cached worklog for %s" % issue.key)
				return self.cached_worklogs[issue.key]
			else:
				logging.debug("No cache found for %s, requesting from Jira. This could take some time." % issue.key)
				self.cached_worklogs[issue.key] = self.jira.worklogs(issue)
				return self.cached_worklogs[issue.key]
		else:
			return self.jira.worklogs(issue)

	def getWorklogSumForIssueForDate(self,issue,date,user=username):
		# date must be a datetime object
		work_time_in_seconds_for_issue = 0.00

		worklogs = self.getWorklog(issue)
		for worklog in worklogs:
			if worklog.author.key == user:
				wdate = self.convertISO8601DateToDateTime(worklog.started)
				if wdate.day == date.day and wdate.month == date.month and wdate.year == date.year:
					work_time_in_seconds_for_issue += worklog.timeSpentSeconds

		logging.info("%d hours shown for %s on %s" % ( self.convertSeconds(work_time_in_seconds_for_issue),issue,date))
		return work_time_in_seconds_for_issue

	def getWorklogSumForDate(self,date):
		sum_seconds = 0
		worklog_issues = self.jira.search_issues('worklogAuthor=%s and worklogDate="%s"' % (username,date.strftime('%Y/%m/%d')), maxResults=50)
		for issue in worklog_issues:
			logging.debug("Getting worklog sum for %s" % date)
			sum_seconds += self.getWorklogSumForIssueForDate(issue,date)

		return sum_seconds

	def getWorklogSumForDates(self, begin=begin_date, end=end_date, user=username):
		worklog_issues = self.jira.search_issues('worklogAuthor=%s and worklogDate >= "%s" and worklogDate <= "%s"' \
			% (user, begin.strftime('%Y/%m/%d'), end.strftime('%Y/%m/%d')), maxResults=50)
		
		return self.getWorklogSumForTicketsInRange(worklog_issues,user,begin,end)


	def getWorklogSumForTicketsInRange(self,ticket_list,user=username,begin=begin_date,end=end_date):
		sum_seconds = 0.0
		
		for issue in ticket_list:
			worklogs = self.getWorklog(issue)
			for worklog in worklogs:
				if worklog.author.key == user:
					if self.convertISO8601DateToDateTime(worklog.started) <= end and \
						self.convertISO8601DateToDateTime(worklog.started) >= begin:
						sum_seconds += worklog.timeSpentSeconds
		return sum_seconds

	def getRemainingTimeForDate(self,date):
		remaining_seconds = 0
		regular_day_seconds = 8 * 60 * 60
		remaining_seconds = regular_day_seconds - self.getWorklogSumForDate(date)

		if remaining_seconds < 0:
			return 0
		return remaining_seconds

	def getActiveTicketListForDates(self,begin=begin_date,end=end_date,user=username):
		active_tickets = self.jira.search_issues('assignee was not %s before "%s" AND assignee was %s before "%s"' \
			% (user, begin.strftime('%Y/%m/%d'), user, end.strftime('%Y/%m/%d')))
		if compatible_projects_keys:
			for index,ticket in enumerate(active_tickets):
				if ticket.fields.project.key not in compatible_projects_keys:
					logging.warning("Removed %s from active tickets" % ticket.key)
					active_tickets.pop(index)
		if not active_tickets:
			logging.info('No tickets found assigned during the given date period.  Consider widening the range of dates to find tickets to assign time to. Exiting')
			sys.exit()
		return active_tickets

	def getWorkingDaysWithinDates(self,begin=begin_date,end=end_date):
		return workdays.networkdays(begin,end)

	def getTimeAllotment(self,begin=begin_date,end=end_date):
		leftover_seconds=  (self.getWorkingDaysWithinDates(begin,end) * 8.0 * 60.0 * 60.0) - self.getWorklogSumForDates(begin,end)
		if leftover_seconds > 0:
			return leftover_seconds #/ 60.0 / 60.0
		else:
			return 0.0

	def addWorkLog(self,log_day,issue="",timeSpent="1h",):
		# Must add timezone for JIRA api to accept
		d = log_day.replace(tzinfo=nyctz())

		logging.info("Reporting %s time on issue %s for day %s" % (timeSpent,issue,d))
		self.jira.add_worklog(issue=issue,timeSpent=timeSpent,started=d)

	def fillOutWorklogForMe(self,begin=begin_date,end=end_date):
		# Query for all tickets assigned between those dates
		my_active_tickets = self.getActiveTicketListForDates(begin,end)
		# Figure out total amount of hours left to be recorded
		total_seconds_unrecorded = self.getTimeAllotment()
		logging.debug("Total seconds to be logged %s" % total_seconds_unrecorded)
		time_per_ticket = total_seconds_unrecorded / len(my_active_tickets)
		logging.info("Work hours to be allocated to each ticket %s" % time_per_ticket)
		leftover_tickets = []
		for ticket in my_active_tickets:
			leftover_tickets.append({'ticket':ticket,'time':time_per_ticket})

		logging.debug("Leftover tickets: %s" % leftover_tickets)

		date_range = self.getWorkDayRange(begin,end)

		for day in date_range:
			logging.debug("--> Working on day: %s <--" % day)
			day_is_full = False
			maxc = 0
			while not day_is_full and maxc < 20:
				maxc += 1
				logging.debug("Leftover tickets in loop: %s" % leftover_tickets)
				for index,leftover_ticket in enumerate(leftover_tickets):
					timeleft = self.getRemainingTimeForDate(day)
					logging.info("Time left in day: %s" % timeleft)
					if timeleft > 0:
						if leftover_ticket['time'] > timeleft:
							logging.debug("Time left in %s exceeds time left in day" % leftover_ticket['ticket'])
							leftover_ticket['time'] -= timeleft
							self.addWorkLog(issue=leftover_ticket['ticket'],\
								timeSpent=self.convertWorkTime(timeleft),\
								log_day=day)
							day_is_full = True
						elif leftover_ticket['time'] == timeleft:
							logging.debug("Time left in %s equals time left in day" % leftover_ticket['ticket'])
						 	leftover_tickets.pop(index)
						 	self.addWorkLog(issue=leftover_ticket['ticket'],\
								timeSpent=self.convertWorkTime(timeleft),\
								log_day=day)
						 	day_is_full = True
						elif leftover_ticket['time'] < timeleft:
							logging.debug("Time left in %s is less than time left in day. Moving to next ticket" % leftover_ticket['ticket'])
							print leftover_ticket['time']
							print self.convertWorkTime(leftover_ticket['time'])
							self.addWorkLog(issue=leftover_ticket['ticket'],\
								timeSpent=self.convertWorkTime(leftover_ticket['time']),\
								log_day=day)
							leftover_tickets.pop(index)
					else:
						break

		# self.getWorklogSumForTicketsInRange(my_active_tickets)

	def printIntro(self):
		printed = ("Welcome to Worklogger.",
			"This script will 1)look for all tickets assigned to you within a give date range",
			"2) Figure out how much time left needs to be recorded",
			"3) Evenly distribute the time left in worklogs to be recorded among the tickets.",
			"\n",
			"It is HIGHLY recommended that you do two things first:",
			"1) Fill out your vacation and scrum times ",
			"2) Avoid running this script during peak Jira hours as it makes a LOT of queries\n",
			# "This script will attempt to do quite a bit of work for you.  It will default to making",
			# "a dry run first, to prevent unwanted changes that might be annoying to fix.",
			"\n\n\n",
			)
		print "\n".join(printed)


if __name__ == '__main__':

	filler = WorklogFiller()
	filler.printIntro()
	filler.fillOutWorklogForMe()

