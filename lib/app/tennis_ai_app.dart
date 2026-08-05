import 'package:flutter/material.dart';
import 'package:tennis_ai/features/home/presentation/home_screen.dart';

class TennisAiApp extends StatelessWidget {
  const TennisAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Tennis AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2E7D32)),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
