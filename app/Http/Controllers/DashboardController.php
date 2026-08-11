<?php

namespace App\Http\Controllers;

use App\Models\Parte;

class DashboardController extends Controller
{
    public function __invoke()
    {
        return redirect()->route('partes.create');
    }
}
