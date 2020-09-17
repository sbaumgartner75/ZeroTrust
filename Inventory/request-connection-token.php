<?php
    if (!isset($_SERVER['SSL_CLIENT_M_SERIAL'])) {
      header('HTTP/1.0 403 Forbidden');
      echo('Nothing to see, move it along!');
      exit();
    }
    require_once('config.php');

    try {
      $pdo = new PDO('mysql:host='.DBHOST.';dbname='.DBNAME.';charset=utf8', DBUSER, DBPASS);
    } catch(PDOException $e) {
      print "Error: ".$e->getMessage()."<br>";
      die();
    }

    require_once('functions.php');

    $serialnumber = $_SERVER['SSL_CLIENT_M_SERIAL'];
    if (! preg_match('/[A-Fa-f0-9]+/', $serialnumber)) {
       die("Error in serial number");
    }

    $token = random_str(32);
    $sql = "UPDATE assets SET connection_token = :token, connection_token_issued = NOW() WHERE certificate_serial_number = :serialnumber";

    $stmt = $pdo->prepare($sql);
    $stmt->execute(array("token" => $token, "serialnumber" => $serialnumber));
    if ($stmt->rowCount() == 1) {
      header('Content-Type: application/json');
      echo json_encode($token);
    } else {
      header('HTTP/1.0 403 Forbidden');
      echo('Nothing to see, move it along!');
    }
    $stmt = Null;
    $pdo = Null;
?>
