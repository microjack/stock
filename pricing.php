<?php

$price = $argv[1];
$money = $argv[2];

$basic_price = 28.3;
$basic_num   = 23000;

$total_money = $basic_price * $basic_num + $money;
$total_num   = intval($basic_num + $money / $price);


$avg_price = number_format($total_money / $total_num, 2);
echo $avg_price . "\r\n";
