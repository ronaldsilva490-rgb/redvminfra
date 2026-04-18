<?php
// You can do some initialization for the template here
@date_default_timezone_set(date_default_timezone_get());
?>
<!doctype html>
<html lang="pt-BR">

<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet" />
<link rel="icon" href="assets/favicon.ico" sizes="any" />
<link title="RED Rapidleech" href="templates/red/styles/rl_style_pm.css" rel="stylesheet" type="text/css" />

<title><?php
if (!isset($nn)) $nn = "\r\n";
if (!isset($page_title)) {
	echo 'RED Rapidleech v2 rev. '.$rev_num;
} else {
	echo htmlspecialchars($page_title);
}
?></title>
<script type="text/javascript">
/* <![CDATA[ */
var php_js_strings = [];
php_js_strings[87] = " <?php echo lang(87); ?>";
php_js_strings[281] = "<?php echo lang(281); ?>";
pic1= new Image();
pic1.src="templates/red/images/ajax-loading.gif";
/* ]]> */
</script>
<script type="text/javascript" src="classes/js.js"></script>
<?php
if ($options['ajax_refresh']) { echo '<script type="text/javascript" src="classes/ajax_refresh.js"></script>'.$nn; }
if ($options['flist_sort']) { echo '<script type="text/javascript" src="classes/sorttable.js"></script>'.$nn; }
?>

</head>

<body>
<div class="red-app-shell">
	<header class="red-app-header">
		<div class="red-brand">
			<img src="assets/logo.png" alt="RED Systems" />
			<div class="red-brand-copy">
				<div class="eyebrow">TRANSFER HUB</div>
				<strong>RED Rapidleech</strong>
				<span>Transferencia remota, uploads e gestao de arquivos com a mesma identidade visual da stack RED.</span>
			</div>
		</div>
		<div class="red-brand-meta">
			<div class="red-status-pill">PHP legado oficializado na stack</div>
			<small>Rev. <?php echo htmlspecialchars($rev_num); ?> • tema RED • base path pronta para /rapidleech/</small>
		</div>
	</header>
	<main class="red-app-main">
