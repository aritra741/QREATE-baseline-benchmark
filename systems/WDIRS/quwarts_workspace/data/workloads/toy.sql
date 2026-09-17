SELECT player.name FROM player WHERE player.position = 'Guard';
SELECT SUM(player.salary) FROM player WHERE player.position = 'Guard';
SELECT AVG(player.salary) FROM player;
SELECT COUNT(*) FROM player;
SELECT player.name FROM player WHERE player.team_id NOT IN (SELECT team.id FROM team WHERE team.city = 'Boston');
SELECT AVG(player.salary) FROM player WHERE player.position = 'Guard';
