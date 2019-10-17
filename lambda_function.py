import requests
import boto3 
import datetime 
import dateutil.parser 
import numpy as np 
import matplotlib.pyplot as plt 
import io 
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from boto3.dynamodb.conditions import Key 
import re
from bs4 import BeautifulSoup



accuweather_api_key = 'your accuweather api key here (trial version suffices)'
darksky_key = 'your darksky api key here (trial version surely suffices'


ACCESS_KEY = 'your aws access key here'
SECRET_KEY = 'your aws secret access key here'
REGION = 'us-east-1'

s3 = boto3.resource('s3',
                    aws_access_key_id=ACCESS_KEY,
                    aws_secret_access_key=SECRET_KEY,
                    region_name=REGION)

dynamodb = boto3.resource('dynamodb',
                          aws_access_key_id=ACCESS_KEY,
                          aws_secret_access_key=SECRET_KEY,
                          region_name=REGION)

table_user = dynamodb.Table('variable_storage')

lambda_ = boto3.client('lambda',
                      aws_access_key_id=ACCESS_KEY,
                      aws_secret_access_key=SECRET_KEY,
                      region_name=REGION)



def plotforecast(loc_key=None,lat_long=None,temp_scale='F',precision='prox'): # this generates the weather template as a matplotlib figure object
  temperature = []  
  rel_humidity = [] 
  wind_speed = [] 
  rain_probability = []
  military_hour = []
  icon_phrases = [] # this will be useful for determining color of stems in stemplot

  if precision=='nabe': # neighborhood precision based on Accuweather, uses zip code
    # Accuweather has a separate api call for current conditions 
    current_response = requests.get('http://dataservice.accuweather.com/currentconditions/v1/{}?apikey={}&details=true'.format(loc_key,accuweather_api_key))
    # appends values  
    rel_humidity.append(current_response.json()[0]['RelativeHumidity']) 
    rain_probability.append(100*current_response.json()[0]['HasPrecipitation'])
    military_hour.append(datetime.datetime.fromtimestamp(current_response.json()[0]['EpochTime']).strftime('%-I %p'))
    wind_speed.append(current_response.json()[0]['Wind']['Speed']['Imperial']['Value'])
    # temperature values come in fahrenheit so this does a conversion in case user opts for celsius
    if temp_scale=='C':
      temperature.append(round((current_response.json()[0]['Temperature']['Imperial']['Value']-32)*(5/9)))
    else:
      temperature.append(round(current_response.json()[0]['Temperature']['Imperial']['Value']))

    # same as before but does it for each hour in the 12 hr forecast
    hourly_response = requests.get('http://dataservice.accuweather.com/forecasts/v1/hourly/12hour/{}?apikey={}&details=true'.format(loc_key,accuweather_api_key))
    for hour in hourly_response.json():
      rel_humidity.append(hour['RelativeHumidity'])
      wind_speed.append(hour['Wind']['Speed']['Value'])
      rain_probability.append(hour['RainProbability'])
      military_hour.append(dateutil.parser.parse(hour['DateTime']).strftime('%-I %p'))
      icon_phrases.append(hour['IconPhrase'])
      if temp_scale=='C':
        temperature.append(round((hour['Temperature']['Value']-32)*(5/9)))
      else:
        temperature.append(round(hour['Temperature']['Value']))
      
  else: # proximity precision based on Dark Sky Api, uses latitude/longitude coordinates
    response = requests.get('https://api.darksky.net/forecast/{}/{}?exclude=currently,daily,minutely,alerts,flags'.format(darksky_key,lat_long))
    # appends values
    for hour in response.json()['hourly']['data']:
      military_hour.append(datetime.datetime.fromtimestamp(hour['time']).strftime('%-I %p'))
      rel_humidity.append(int(round(100*hour['humidity'],0)))
      wind_speed.append(hour['windSpeed'])
      rain_probability.append(int(round(100*hour['precipProbability'],0)))
      # the icon phrase entries for Dark Sky are not there if precipProbability == 0
      try:
        icon_phrases.append(hour['precipType'].capitalize())
      except KeyError:
        icon_phrases.append('None')

      if temp_scale=='C':
        temperature.append(round((hour['temperature']-32)*(5/9)))
      else:
        temperature.append(round(hour['temperature']))

    # Dark Sky gives first 48 hours; we just need the current + the future 12 hours
    military_hour = military_hour[:13]
    rain_probability = rain_probability[:13]
    wind_speed = wind_speed[:13]
    rel_humidity = rel_humidity[:13]
    temperature = temperature[:13]

  fig, ax = plt.subplots(1,1,figsize=(16,5)) # prepares figure and axes objects
  fig.patch.set_facecolor('xkcd:powder blue') # adds light blue background to canvas
   


  ax.plot(np.arange(1,len(military_hour)+1), temperature, color='gold', marker='o', # plots temperature time series  
  		zorder=-1) # hide lines and intersections behind scatterpoints

  ax.fill_between(np.arange(1,len(military_hour)+1), temperature, color='gold', alpha=0.4) # shades area underneath temperature ts
  ax.set_xticks(np.arange(1,len(military_hour)+1)) # sets relevant x-ticks
  ax.set_xticklabels(military_hour, rotation=45) # converts those x-ticks to the labels and rotates them 
  ax.set_ylim(min(temperature)-5, max(temperature)+3) # adjusts y-axis range 
  ax.set_yticks(np.arange(min(temperature)-2, max(temperature)+3)) # sets relevant y-ticks plus some extra ticks
  ax.set_yticklabels([int(temp_tick) for temp_tick in ax.get_yticks()]) 

  ax2 = ax.twinx() # prepares a twin y axis with x-axis having in common
  ax2.set_yticks(np.linspace(min(temperature)-5, min(temperature)-1,6)) # sets relevant y-ticks for rain probability in a reasonable region below temp ts
  ax2.set_ylim(ax.get_ylim()) # fixes bug so that ax2 properly appears opposite of ax
  ax2.set_yticklabels([str(int(percentage))+'%' for percentage in 100*np.arange(0,1.2,0.2)]) # converts y-ticks for ax2 to 0%, 20%, 40%, ... 100%
  markerline, stemlines, baseline = ax2.stem(np.arange(1,len(military_hour)+1), # prepares artist objects for modification
  									min(temperature)-5+0.04*np.asarray(rain_probability),linefmt=':') # plots dotted stem plots for rain probability
  for stemobj in (markerline,stemlines,baseline):
    plt.setp(stemobj,'zorder',2)
  plt.setp(stemlines,'linewidth',3) # changes stem width using the stemlines artist object
  plt.setp(markerline,'color','b') # changes tip/marker color using markerline artist object

  if precision=='nabe': # current hour for 'nabe' has a variable iconPhrase option; no point in hard coding it. 
    stemlines = stemlines[1:] # instead ignore current hour and obtain a 1-1 correspondence with the icon_phrases
  else: # if this is 'prox', 1-1 correspondence is already established
    pass

  for stem,icon in zip(stemlines,icon_phrases):
    if ('Flurries' in icon.split()) or ('Snow' in icon.split()) or ('Ice' in icon.split()) or ('Sleet' in icon.split()) and not ('Rain' in icon.split()):
      plt.setp(stem,'color','white') # changes stem color to white if any of these key words pop up
    elif (('Snow' in icon.split()) and ('Rain' in icon.split())) or ('Freezing' in icon.split()): 
      plt.setp(stem,'color','cornflowerblue') # changes stem color to cornflowerblue if the key word is a mix of rain and snow
    else:
      plt.setp(stem,'color','b') # changes every other stem to blue (there's pretty much snow, snow/rain mix, and rain categories as precipitation)



  noaadata_maximums = np.array([14.27, 14.02, 13.97, 11.67, 9.62, 9.54, 8.3, 8.36, 9.25, 11.91, 11.88, 13.01]) # represents 9-year average (2010-2018) of monthly (jan-dec) maximums/minimums of daily means for wind speed. 
  noaadata_minimums = np.array([3.06, 2.77, 3.18, 2.75, 1.84, 2.21, 2.24, 1.78, 1.46, 1.79, 2.18, 2.2]) # data obtained from noaa's local climatological dataset for a weather station in central park.
  max_now = noaadata_maximums[datetime.datetime.now().month-1] # january are the first entries in the former lists. But first entries start from 0 in python
  min_now = noaadata_minimums[datetime.datetime.now().month-1]

  scatter_object = ax.scatter(np.arange(1,len(military_hour)+1),temperature, # plots scatterplot, prepares artist object
  							s = [(50*(ws-min_now)/(max_now-min_now))**2 if (ws<max_now) and (ws>min_now+1) else \
  							(50**2 if ws>=max_now else 0) for ws in wind_speed], # size of circles represent wind speed, those near the min will be about the size of the regular dots
  							# 50 is an arbitary scaling value and I do min-max scaling based on the noaa data.
  							c = np.asarray(rel_humidity),cmap='RdYlBu_r', # color represents humidity
  							edgecolors = (0.933333,0.780392,0), # rgb tuple so its a shade darker than gold
  							zorder = 1)  # bring scatterplot to the front and ignore lines behind


  rel_hum_cbar = fig.colorbar(scatter_object,ax=ax,pad=0.07) # plots colorbar for rel_humidity using scatter object; prepares colorbar artist object
  #rel_hum_cbar.ax.set_yticklabels([str(number.get_text())+'%' for number in rel_hum_cbar.ax.get_yticklabels()],fontname=font) # attaches percentage sign to colorbar ticks 
  rel_hum_cbar.set_label('Relative Humidity (%)', rotation=270,labelpad=19,color='darkorange',fontsize=14) # gives the rel_humidity a proper label


  ax.set_title('Current and 12 Hour Forecast',loc='center', fontsize=15) # title of figure
  ax.set_ylabel(r'Temperature ($^\circ {}$)'.format(temp_scale), color = 'gold',fontsize=14) # temperature y-axis title
  ax2.set_ylabel('Precipitation Probability',rotation=270,color='b') # precip prob y-axis title
  ax2.yaxis.set_label_coords(1.075,0.15) # properly aligns precip prob title to ticks 


  wind_speed = np.asarray(wind_speed) # some numpy functions used henceforth will require input as arrays
  circle_min = plt.scatter([],[], c='gold',linewidths=2) # scatter object for minimum of that month
  # scatter object for median size wind_speed (median is a good measure of central tendency for skewed data (not necessarily symmetric))
  circle_data_median = plt.scatter([],[], s=(50*(np.median(wind_speed)-min_now)/(max_now-min_now))**2,edgecolors=(0.933333,0.780392,0), color='None',linewidths=2)
  circle_max = plt.scatter([],[], s=50**2, edgecolors=(0.933333,0.780392,0), color='None',linewidths=2) # scatter object for maximum of that month
  circle_other = list(set(scatter_object.get_sizes())-{0,50**2}-{np.abs(wind_speed-np.median(wind_speed)).min()}) # get sizes of scatter_object and remove min and max sizes 
                                                                                                                  # as well the one closes to the median 

  circle_object_list = [circle_min] # create a list of scatter objects, starting with the minimum (so they're in order when they're plotted later)
  circle_size_list = [r'$\leq${}'.format(round(min_now+1,2))] # create a list of strings (descriptive of the wind speed), starting with the minimum (so they're in order when they're plotted later)

  if len(circle_other)>1: # if the length of circle_other is more than 1, we'll choose 2 or 2 randomly 
    first_random_idx = np.random.randint(len(circle_other)) # generate a random index up to len(circle_other) exclusive  
    circle1 = circle_other[first_random_idx] # access (according to that index) circle_other and save as the first cirle object other than min,max and median
    circle2 = circle_other[np.random.choice(list(set([i for i in range(len(circle_other))])-{first_random_idx}))] # second circle object other than min,max and median

    for circle in (circle1,circle2):
      if circle<circle_data_median.get_sizes()[0]: # if circle in (circle1,circle2) is less than the median, it ought to come before in the list
        circle_object_list.append(plt.scatter([],[],s=circle,edgecolors=(0.933333,0.780392,0), color='None',linewidths=2)) # append scatter object with size circle, since circle is just a size
        circle_size_list.append(str(round(min_now+pow(circle,0.5)*((max_now-min_now)/50),2))) # inverse transformation of min max scaling to get back associated wind speed

    circle_object_list.append(circle_data_median) # now append median scatter object 
    circle_size_list.append(str(round(np.median(wind_speed),2))) # and append associated wind speed


    for circle in (circle1,circle2): # same as before but checks if there are any circles with sizes greater than the median so they get appended AFTER the median has been
      if circle>circle_data_median.get_sizes()[0]:
        circle_object_list.append(plt.scatter([],[],s=circle,edgecolors=(0.933333,0.780392,0), color='None',linewidths=2))
        circle_size_list.append(str(round(min_now+pow(circle,0.5)*((max_now-min_now)/50),2)))

    circle_object_list.append(circle_max) # lastly, appends the max scatter object
    circle_size_list.append(r'$\geq${}'.format(max_now)) # and appends associated wind speed inequality 

  elif len(circle_other)==1: # if circle_other has length 1, append that circle and the max
    circle_object_list.append(plt.scatter([],[],s=circle_other[0],edgecolors=(0.933333,0.780392,0), color='None',linewidths=2))
    circle_size_list.append(str(round(min_now+pow(circle_other[0],0.5)*((max_now-min_now)/50),2)))
    circle_object_list.append(circle_max)
    circle_size_list.append(r'$\geq${}'.format(max_now))

  else: # if there are no elements in circle_other, then just top it off with the maximum circle object and string
    circle_object_list.append(circle_max)
    circle_size_list.append(r'$\geq${}'.format(max_now))


  legend = ax.legend(circle_object_list, # the handles, or the scatter objects 
         circle_size_list, # the labels, or the associated wind speeds
         scatterpoints=1, # display only 1 of each
         loc='center left', # the rest is to control for aesthetics 
         ncol=1,
         fontsize=9,
         labelspacing=5,
         bbox_to_anchor=(1.2, 0.5),
         borderpad=2,
         handletextpad=3,
         title='Wind Speed (mph)')

  legend._legend_box.sep = 10 
  plt.setp(legend.get_title(),color='cornflowerblue') # make title for wind speed cornflowerblue
  return fig # return figure object containing info about everything we did to it


def mtaservicestatuschecker(subwaygroup):
	# note: this only returns if there are no issues for the requested subwaygroup (aka 'Good Service')
	# or all the planned work entries for that subwaygroup if they exist
	# still need to do the other cases (delays, part suspended, etc)
	assert isinstance(subwaygroup,str)
	source = requests.get('http://www.mta.info/status/subway/{}'.format(subwaygroup)).text #use NQR ommitting W
	soup = BeautifulSoup(source,'lxml')
	match = soup.find('div',id='status_display')

	if match.text == "The Service Status has changed. Please go back to the MTA home page for latest status.":
		print('Good Service')
	else:
		if plannedworkinfo != []:
			all_messages = []
			for plannedworks in plannedworkinfo:
				message = list()
				for text in plannedworks.find_all(string=True):
					if text.find_previous_siblings('img') == []:
						message.append(text)
					else:
						msg_with_train = str()
						siblings = text.find_previous_siblings()[::-1]
						nearestimgsiblings = siblings[[idx for idx,sibl in enumerate(siblings) if sibl.name=='br'][-1]+1:] # this works if there are no bolded letters <strong></strong>
						if nearestimgsiblings == []:
							message.append(text)
						else:
							for img in nearestimgsiblings:
								msg_with_train+=img['alt'][0]+','
						message.append(msg_with_train[:-1]+text)
				all_messages.append(' '.join(message))
			return all_messages



def lambda_handler(event,context):
	message_body = event['body']
	from_number = event['from_number']
	dynamo_response = table_user.query(TableName='variable_storage',
									KeyConditionExpression=Key('phone_number').eq(from_number))

	if dynamo_response['Count'] == 0:
		table_user.put_item(Item={'phone_number':from_number})
		return '<Body>Welcome to the GetReady app! '\
		'Please provide the required initial values. This can be done by visiting '\
		'{} and following the associated directions. '\
		'You can always refer to the link which contains the list of available commands by submitting ;help' \
		'At any point you decide to quit with the app, send ;quit </Body>'.format('[github link with instructions here]') # add github header initialization directions link
	else:
		quit = re.compile(r';(quit)()')
		if quit.findall(message_body) != []:
			table_user.delete_item(Key={'phone_number':from_number})
			return '<Body>Account cleared!</Body>'

		prox = re.compile(r';(prox)()')
		nabe = re.compile(r';(nabe)()')
		help_ = re.compile(r';(help)()')
		zip_code = re.compile(r';(zipcode)\s?=\s?(\d{5})')
		lat_long = re.compile(r';(latlong)\s?=\s?(-?\d{1,2}\.\d{4},-?\d{1,3}\.\d{4})')
		C_F = re.compile(r';(CF)\s?=\s?([CF])')
		rainthres = re.compile(r';(rainthres)\s?(=?)\s?([~^]?)\s?([7-9][0-9])?')
		mta_alerts = re.compile(r';(mta_alerts)\s?(=?)\s?([~^]?)\s?([1-7A-GJL-NQRWZ,]*)?')
		crontime = re.compile(r';(crontime)\s?=\s?([~^]?)\s?(([1-7]-?[1-7]?)#(\d{2}):(\d{2}))?')



		pattern_attribute_values = dict()
		pattern_expression = 'set '
		for idx,ptrn in enumerate((nabe,prox,help_,rainthres,mta_alerts,zip_code,lat_long,C_F,crontime)):
			pattern = ptrn.findall(message_body)
			if pattern != []:
				if pattern[0][0] == 'nabe': # short for neighborhood (based on zip code), utilizes accuweather api
					try:
						canvas = FigureCanvas(plotforecast(precision='nabe',
														temp_scale=dynamo_response['Items'][0]['CF'],
														loc_key=dynamo_response['Items'][0]['zipcode']))
						img_data = io.BytesIO() # prepares binary stream object 
						canvas.print_png(img_data) # pastes picture onto binary stream object 
						s3.Object('weather-templates','hourly.png') \
						      .put(Body=img_data.getvalue(),ContentType='image/png') # puts the image in S3 bucket that is https link retrievable
						s3.ObjectAcl('weather-templates','hourly.png').put(ACL='public-read')
						url = 'https://weather-templates.s3.amazonaws.com/hourly.png' # https link
						return '<Media>{}</Media>'.format(url) # sends url to twilio for image preprocessing before being sent to user
					except Exception:
						return '<Body>You need to enter the necessary entries</Body>'

				elif pattern[0][0] == 'prox': # short for proximity (based on geographical position on Earth), utilizes Dark Sky 
					try:
						canvas = FigureCanvas(plotforecast(precision='prox',
														temp_scale=dynamo_response['Items'][0]['CF'],
														lat_long=dynamo_response['Items'][0]['latlong']))
						img_data = io.BytesIO() 
						canvas.print_png(img_data)
						s3.Object('weather-templates','hourly.png') \
						      .put(Body=img_data.getvalue(),ContentType='image/png')
						s3.ObjectAcl('weather-templates','hourly.png').put(ACL='public-read')
						url = 'https://weather-templates.s3.amazonaws.com/hourly.png'
						return '<Media>{}</Media>'.format(url)
					except Exception:
						return '<Body>You need to enter the necessary entries</Body>'

				elif pattern[0][0] == 'help':
					return '<Body>{}</Body>'.format('[github link with list of commands here]')

				elif pattern[0][0] == 'rainthres': # this still needs work !!!
					if '=' not in pattern[0]:
						pass # here return the 1 hr minbymin prediction
					else:
						if ('~' not in pattern[0]) and ('^' not in pattern[0]):
							pattern_expression+='rainthres[0] = :{}, '.format(str(idx))
							pattern_attribute_values.update({':'+str(idx):pattern[0][-1]})
						else:
							pattern_expression+='rainthres[1] = :{}, '.format(str(idx))
							pattern_attribute_values.update({':'+str(idx):pattern[0][-2]})

				elif pattern[0][0] == 'mta_alerts': 
					if '=' not in pattern[0]:
						pattern123 = re.compile(r'[1-3]')
						pattern456 = re.compile(r'[4-6]')
						pattern7 = re.compile(r'[7]')
						patternACE = re.compile(r'[ACE]')
						patternBDFM = re.compile(r'[BDFM]')
						patternG = re.compile(r'[G]')
						patternJZ = re.compile(r'[JZ]')
						patternL = re.compile(r'[L]')
						patternNQRW = re.compile(r'[NQRW]')
						patternS = re.compile(r'[S]')
						subways = [('123',pattern123),('456',pattern456),('7',pattern7),
						           ('ACE',patternACE),('BDFM',patternBDFM),('G',patternG),
						          ('JZ',patternJZ),('L',patternL),('NQR',patternNQRW),
						          ('S',patternS)]

						all_subways_alert = []
						for tag,pattern in subways:
						    seen_subways = pattern.findall(dynamo_response['Items'][0]['mta_alerts'])
						    if seen_subways != []:
						        all_subways_alert.append((' '.join(seen_subways),mtaservicestatuschecker(subwaygroup=tag)))
						return '<Body>'+str(all_subways_alert)+'</Body>'
						
					else:
						if ('~' not in pattern[0]) and ('^' not in pattern[0]):
							pattern_expression+='mta_alerts[0] = :{}, '.format(str(idx))
							pattern_attribute_values.update({':'+str(idx):pattern[0][-1]})
						else:
							pattern_expression+='mta_alerts[1] = :{}, '.format(str(idx))
							pattern_attribute_values.update({':'+str(idx):pattern[0][-2]})

				elif pattern[0][0] == 'zipcode':
					loc_key = requests.get('http://dataservice.accuweather.com/locations/v1/search?q={}&apikey={}'.format(pattern[0][-1],accuweather_api_key))
					loc_key = loc_key.json()[0]['Key']
					pattern_expression+='zipcode = :{}, '.format(str(idx))
					pattern_attribute_values.update({':'+str(idx):loc_key})

				elif pattern[0][0] == 'latlong':
					pattern_expression+='latlong = :{}, '.format(str(idx))
					pattern_attribute_values.update({':'+str(idx):pattern[0][-1]})

				elif pattern[0][0] == 'CF':
					pattern_expression+='CF = :{}, '.format(str(idx))
					pattern_attribute_values.update({':'+str(idx):pattern[0][-1]})

				elif pattern[0][0] == 'crontime': # this feature needs work !!! 
					if ('~' not in pattern[0]) and ('^' not in pattern[0]):
						cronexpression = 'cron({} {} ? * {} *)'.format(int(pattern[0][-1]),int(pattern[0][-2])+4,pattern[0][-3])
						pattern_expression+='crontime[0] = :{}, '.format(str(idx))
						pattern_attribute_values.update({':'+str(idx):cronexpression})
					else:
						pattern_expression+='crontime[1] = :{}, '.format(str(idx))
						pattern_attribute_values.update({':'+str(idx):pattern[0][1]})

		if pattern_expression != 'set ': 
			dynamodb.Table('variable_storage').update_item(Key={'phone_number':from_number},
	                                          				UpdateExpression=pattern_expression[:-2],
	                                        				ExpressionAttributeValues=pattern_attribute_values)
			return '<Body>Your entries have been saved.</Body>'
			

# © Matthew K