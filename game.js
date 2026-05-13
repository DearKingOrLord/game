# Mario-Style Game (HTML + CSS + JavaScript)

## 📁 Создай один файл: `index.html`

Вставь весь код ниже:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mini Mario</title>

<style>

body {
    margin: 0;
    overflow: hidden;
    background: linear-gradient(#6ec6ff, #d9f0ff);
    font-family: Arial, sans-serif;
}

canvas {
    display: block;
    margin: auto;
    background: #87CEEB;
}

#info {
    position: fixed;
    top: 10px;
    left: 10px;
    color: white;
    background: rgba(0,0,0,0.5);
    padding: 10px;
    border-radius: 10px;
}

</style>
</head>
<body>

<div id="info">
    <h2>Mini Mario</h2>
    <p>A / D — движение</p>
    <p>W или Space — прыжок</p>
</div>

<canvas id="game"></canvas>

<script>

const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');

canvas.width = 1000;
canvas.height = 500;

// ===== ИГРОК =====

const player = {
    x: 100,
    y: 300,
    width: 40,
    height: 50,
    color: 'red',

    velocityX: 0,
    velocityY: 0,

    speed: 5,
    jumpForce: 14,

    grounded: false
};

// ===== ФИЗИКА =====

const gravity = 0.6;

// ===== УПРАВЛЕНИЕ =====

const keys = {};

window.addEventListener('keydown', (e) => {
    keys[e.key.toLowerCase()] = true;

    if((e.key === 'w' || e.code === 'Space') && player.grounded) {
        player.velocityY = -player.jumpForce;
        player.grounded = false;
    }
});

window.addEventListener('keyup', (e) => {
    keys[e.key.toLowerCase()] = false;
});

// ===== ПЛАТФОРМЫ =====

const platforms = [
    {x:0, y:450, width:1000, height:50},

    {x:200, y:360, width:120, height:20},
    {x:400, y:300, width:120, height:20},
    {x:600, y:240, width:120, height:20},
    {x:820, y:180, width:120, height:20},

    {x:1150, y:380, width:200, height:20},
    {x:1450, y:320, width:150, height:20},
    {x:1750, y:250, width:200, height:20},

    {x:2100, y:420, width:400, height:30}
];

// ===== МОНЕТЫ =====

const coins = [
    {x:240, y:320, size:20, collected:false},
    {x:440, y:260, size:20, collected:false},
    {x:640, y:200, size:20, collected:false},
    {x:850, y:140, size:20, collected:false},
    {x:1500, y:280, size:20, collected:false},
    {x:1820, y:210, size:20, collected:false}
];

let score = 0;

// ===== КАМЕРА =====

let cameraX = 0;

// ===== ФЛАГ ПОБЕДЫ =====

const finish = {
    x: 2400,
    y: 320,
    width: 20,
    height: 100
};

let win = false;

// ===== ВРАГИ =====

const enemies = [
    {
        x: 700,
        y: 410,
        width: 40,
        height: 40,
        dir: 1
    },
    {
        x: 1600,
        y: 280,
        width: 40,
        height: 40,
        dir: -1
    }
];

// ===== СТОЛКНОВЕНИЕ =====

function isColliding(a, b) {
    return (
        a.x < b.x + b.width &&
        a.x + a.width > b.x &&
        a.y < b.y + b.height &&
        a.y + a.height > b.y
    );
}

// ===== ОБНОВЛЕНИЕ =====

function update() {

    // ДВИЖЕНИЕ

    player.velocityX = 0;

    if(keys['a']) {
        player.velocityX = -player.speed;
    }

    if(keys['d']) {
        player.velocityX = player.speed;
    }

    player.x += player.velocityX;

    // ГРАВИТАЦИЯ

    player.velocityY += gravity;
    player.y += player.velocityY;

    player.grounded = false;

    // ПЛАТФОРМЫ

    for(let platform of platforms) {

        if(
            player.x < platform.x + platform.width &&
            player.x + player.width > platform.x &&
            player.y + player.height < platform.y + 20 &&
            player.y + player.height + player.velocityY >= platform.y
        ) {
            player.y = platform.y - player.height;
            player.velocityY = 0;
            player.grounded = true;
        }
    }

    // МОНЕТЫ

    for(let coin of coins) {

        if(!coin.collected) {

            if(isColliding(player, {
                x: coin.x,
                y: coin.y,
                width: coin.size,
                height: coin.size
            })) {

                coin.collected = true;
                score++;
            }
        }
    }

    // ВРАГИ

    for(let enemy of enemies) {

        enemy.x += enemy.dir * 2;

        if(enemy.x < enemy.startX - 60 || enemy.x > enemy.startX + 60) {
            enemy.dir *= -1;
        }

        if(isColliding(player, enemy)) {

            // Прыжок сверху
            if(player.velocityY > 0 && player.y < enemy.y) {
                enemy.dead = true;
                player.velocityY = -10;
            }
            else {
                player.x = 100;
                player.y = 300;
            }
        }
    }

    // Удаление врагов

    for(let i = enemies.length - 1; i >= 0; i--) {
        if(enemies[i].dead) {
            enemies.splice(i, 1);
        }
    }

    // КАМЕРА

    cameraX = player.x - 250;

    if(cameraX < 0) {
        cameraX = 0;
    }

    // ПОБЕДА

    if(isColliding(player, finish)) {
        win = true;
    }
}

// ===== РИСОВАНИЕ =====

function draw() {

    ctx.clearRect(0,0,canvas.width,canvas.height);

    // НЕБО

    ctx.fillStyle = '#87CEEB';
    ctx.fillRect(0,0,canvas.width,canvas.height);

    // ОБЛАКА

    ctx.fillStyle = 'white';

    ctx.beginPath();
    ctx.arc(150 - cameraX * 0.2, 100, 30, 0, Math.PI * 2);
    ctx.arc(190 - cameraX * 0.2, 90, 40, 0, Math.PI * 2);
    ctx.arc(240 - cameraX * 0.2, 100, 30, 0, Math.PI * 2);
    ctx.fill();

    // ПЛАТФОРМЫ

    for(let platform of platforms) {

        ctx.fillStyle = '#8B4513';
        ctx.fillRect(
            platform.x - cameraX,
            platform.y,
            platform.width,
            platform.height
        );

        ctx.fillStyle = '#55aa55';
        ctx.fillRect(
            platform.x - cameraX,
            platform.y,
            platform.width,
            6
        );
    }

    // МОНЕТЫ

    for(let coin of coins) {

        if(!coin.collected) {

            ctx.fillStyle = 'gold';

            ctx.beginPath();
            ctx.arc(
                coin.x - cameraX,
                coin.y,
                coin.size / 2,
                0,
                Math.PI * 2
            );
            ctx.fill();
        }
    }

    // ФЛАГ

    ctx.fillStyle = 'black';
    ctx.fillRect(
        finish.x - cameraX,
        finish.y,
        finish.width,
        finish.height
    );

    ctx.fillStyle = 'red';
    ctx.fillRect(
        finish.x - cameraX,
        finish.y,
        50,
        30
    );

    // ВРАГИ

    for(let enemy of enemies) {

        ctx.fillStyle = 'brown';

        ctx.fillRect(
            enemy.x - cameraX,
            enemy.y,
            enemy.width,
            enemy.height
        );
    }

    // ИГРОК

    ctx.fillStyle = player.color;

    ctx.fillRect(
        player.x - cameraX,
        player.y,
        player.width,
        player.height
    );

    // СЧЕТ

    ctx.fillStyle = 'white';
    ctx.font = '30px Arial';
    ctx.fillText('Coins: ' + score, 20, 40);

    // ПОБЕДА

    if(win) {

        ctx.fillStyle = 'rgba(0,0,0,0.7)';
        ctx.fillRect(0,0,canvas.width,canvas.height);

        ctx.fillStyle = 'white';
        ctx.font = '60px Arial';
        ctx.fillText('YOU WIN!', 350, 250);
    }
}

// ===== LOOP =====

function gameLoop() {

    if(!win) {
        update();
    }

    draw();

    requestAnimationFrame(gameLoop);
}

// ФИКС ДЛЯ ВРАГОВ

for(let enemy of enemies) {
    enemy.startX = enemy.x;
}

gameLoop();

</script>

</body>
</html>
