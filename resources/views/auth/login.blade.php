<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Ingreso - Parte de Fuerza</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
</head>
<body class="login-page">
    <form method="POST" action="{{ route('login.store') }}" class="login-card">
        @csrf
        <div class="crest large">PN</div>
        <h1>POLICÍA NACIONAL</h1>
        <p>Sistema Parte de Fuerza</p>
        @if ($errors->any())
            <div class="alert danger">{{ $errors->first() }}</div>
        @endif
        <label>Correo</label>
        <input type="email" name="email" value="{{ old('email', 'admin@policia.local') }}" required autofocus>
        <label>Contraseña</label>
        <input type="password" name="password" required>
        <label class="check"><input type="checkbox" name="remember"> Recordarme</label>
        <button class="btn primary full">Ingresar</button>
        <small>Usuario semilla: admin@policia.local / password</small>
    </form>
</body>
</html>
