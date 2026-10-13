# Data profile: player

Tables (rows = documents): city (29), owner (16), player (141), team (30)

Columns marked INITIAL are read by the initial build; build questions may use ONLY those. Test questions may use any column.

Value statistics are from the correct data (what a perfect extraction would hold). Values containing '||' are lists.

## city.area  [new; number; filled 23/29; distinct 23]
description: area is the area of the city in square kilometers (e.g. 89.64).
most common values: '400.739' x1; '375.78' x1; '121.0' x1; '286.0' x1; '630.2' x1; '1341.0' x1; '177.0' x1; '125.0' x1; '213.6' x1; '1651.0' x1

## city.city_name  [INITIAL; free text; filled 29/29; distinct 29]
description: city_name is the name of the city (e.g. Boston)
most common values: 'Denver' x1; 'Portland' x1; 'San Francisco' x1; 'Philadelphia' x1; 'New Orleans' x1; 'Chicago' x1; 'Orlando' x1; 'Salt Lake City' x1; 'Toronto' x1; 'Phoenix' x1

## city.gdp  [new; free text; filled 7/29; distinct 7]
description: gdp is the gross domestic product of the city in millions (e.g. 7.2).
most common values: '252200' x1; '518.5' x1; '689000' x1; '362000' x1; '102000000000' x1; '473000' x1; '344.9' x1

## city.population  [INITIAL; number; filled 29/29; distinct 29]
description: population is the population of the city (e.g. 7000000).
most common values: '715522' x1; '652503' x1; '808988' x1; '1603797' x1; '383997' x1; '2746388' x1; '307573' x1; '200133' x1; '2794356' x1; '1662607' x1

## city.state_name  [INITIAL; free text; filled 28/29; distinct 22]
description: state_name is the name of the state the city is located in (e.g. California).
most common values: 'California' x4; 'Texas' x3; 'Florida' x2; 'Colorado' x1; 'Oregon' x1; 'Pennsylvania' x1; 'Louisiana' x1; 'Illinois' x1; 'Utah' x1; 'Ontario' x1

## player.age  [INITIAL; number; filled 141/141; distinct 61]
description: age of the player (if death_date is given, compute as death_date - birth_date; otherwise, compute as 2025/1/1 - birth_date).
most common values: '28' x7; '37' x7; '31' x6; '33' x5; '29' x5; '35' x5; '30' x5; '66' x5; '24' x4; '53' x4

## player.birth_date  [new; free text; filled 141/141; distinct 141]
description: birth date of the player; use format YYYY/%-m/%-d (e.g., 1984/2/30).
most common values: '1994/2/2' x1; '1942/9/7' x1; '1992/12/17' x1; '1996/2/23' x1; '1994/3/16' x1; '1990/5/2' x1; '1992/3/23' x1; '1998/3/3' x1; '1995/9/28' x1; '1995/2/23' x1

## player.college  [new; free text; filled 123/141; distinct 92]
description: the college the player attended, if applicable (e.g., Duke University).
most common values: 'UCLA' x8; 'University of Florida' x4; 'University of Connecticut' x3; 'University of Kentucky' x3; 'Michigan State' x3; 'Indiana Hoosiers' x3; 'Duke University' x2; 'University of Missouri' x2; 'Kentucky' x2; 'University of North Carolina at Chapel Hill' x2

## player.draft_pick  [new; number; filled 139/141; distinct 39]
description: the pick number at which the player was selected in the NBA draft (e.g., 1).
most common values: '0' x32; '1' x15; '2' x9; '3' x6; '5' x6; '8' x6; '10' x5; '13' x5; '35' x4; '6' x3

## player.draft_year  [new; number; filled 140/141; distinct 55]
description: the year the player was selected in the NBA draft; use format YYYY (e.g., 2003).
most common values: '0' x26; '2015' x5; '2017' x5; '2012' x5; '1988' x5; '2014' x4; '2023' x4; '2013' x4; '1981' x4; '2016' x3

## player.fiba_world_cup  [new; number; filled 140/141; distinct 3]
description: number of FIBA World Cup titles the player has won (e.g., 1).
most common values: '0' x121; '1' x18; '2' x1

## player.mvp_awards  [INITIAL; number; filled 141/141; distinct 6]
description: number of NBA MVP awards the player has won; use 0 if none (e.g., 2).
most common values: '0' x124; '1' x11; '2' x3; '4' x1; '5' x1; '3' x1

## player.name  [new; free text; filled 141/141; distinct 141]
description: full name of the NBA player (e.g., LeBron James).
most common values: 'Antonius Cleveland' x1; 'Toby Kimball' x1; 'Chavano Rainer "Buddy" Hield' x1; "D'Angelo Russell" x1; 'Joel Hans Embiid' x1; 'Paul Clifton Anthony George' x1; 'Kyrie Andrew Irving' x1; 'Jayson Christopher Tatum' x1; 'Caleb Martin' x1; 'Andrew Christian Wiggins' x1

## player.nationality  [INITIAL; free text; filled 139/141; distinct 22]
description: nationality of the player (e.g., American, France).
most common values: 'American' x116; 'Canadian' x2; 'French' x2; 'Bahamian' x1; 'Cameroonian-American' x1; 'British' x1; 'Greek and Nigerian' x1; 'Dominican' x1; 'American-Chinese' x1; 'Congolese' x1

## player.nba_championships  [new; number; filled 140/141; distinct 9]
description: number of NBA championships the player has won (e.g., 4).
most common values: '0' x107; '1' x18; '2' x4; '4' x4; '5' x3; '3' x1; '6' x1; '13' x1; '9' x1

## player.olympic_gold_medals  [INITIAL; number; filled 140/141; distinct 5]
description: number of Olympic gold medals the player has won (e.g., 3).
most common values: '0' x114; '1' x15; '2' x9; '3' x1; '4' x1

## player.position  [INITIAL; category; filled 76/141; distinct 2]
description: player's primary position on the team; choose one from ['Frontcourt', 'Backcourt'].
most common values: 'Frontcourt' x45; 'Backcourt' x31

## player.team  [INITIAL; free text; filled 139/141; distinct 67]
description: the current NBA team the player belongs to, or the last NBA team the player joined if not currently active.
most common values: 'Golden State Warriors' x11; 'Los Angeles Lakers' x9; 'Philadelphia 76ers' x8; 'Boston Celtics' x7; 'New York Knicks' x7; 'Miami Heat' x6; 'Detroit Pistons' x6; 'San Antonio Spurs' x5; 'Milwaukee Hawks' x4; 'New Orleans Jazz' x3

## team.championship  [INITIAL; free text; filled 30/30; distinct 9]
description: 
most common values: '0' x10; '1' x8; '3' x4; '2' x3; '7' x1; '17' x1; '18' x1; '5' x1; '6' x1

## team.championships  [new; number; filled 0/30; distinct 0]
description: championships is the number of this team getting championships (e.g. 5).
most common values: 

## team.founded_year  [new; number; filled 30/30; distinct 14]
description: founded_year is the year of this team team founded (e.g. 1947).
most common values: '1946' x6; '1967' x6; '1970' x3; '1995' x2; '1988' x2; '1968' x2; '1989' x2; '2002' x1; '1923' x1; '1974' x1

## team.location  [INITIAL; free text; filled 30/30; distinct 29]
description: location is the lastest city the team team located (e.g. Los Angeles).
most common values: 'Los Angeles' x2; 'Atlanta' x1; 'San Francisco' x1; 'Houston' x1; 'Indianapolis' x1; 'Memphis' x1; 'Miami' x1; 'Milwaukee' x1; 'Minneapolis' x1; 'New Orleans' x1

## team.ownership  [new; free text; filled 24/30; distinct 24]
description: ownership is the name of the team's owner (e.g. Jeanie Buss).
most common values: 'Atlanta Spirit LLC' x1; 'Joseph Steven Lacob' x1; 'Tilman Joseph Fertitta' x1; 'Herbert Simon' x1; 'Steven Anthony Ballmer' x1; 'Jerry Buss (from 1979)' x1; 'Robert J. Pera' x1; 'Micky Arison' x1; 'Wes Edens and Marc Lasry' x1; 'Glen Taylor' x1

## team.team_name  [INITIAL; free text; filled 30/30; distinct 30]
description: team_name is the full name of the team (e.g. Los Angeles Lakers).
most common values: 'Atlanta Hawks' x1; 'Golden State Warriors' x1; 'Houston Rockets' x1; 'Indiana Pacers' x1; 'Los Angeles Clippers' x1; 'Los Angeles Lakers' x1; 'Memphis Grizzlies' x1; 'Miami Heat' x1; 'Milwaukee Bucks' x1; 'Minnesota Timberwolves' x1
