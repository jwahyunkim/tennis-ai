import 'package:flutter/material.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Tennis AI')),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.sports_tennis,
                  size: 88,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(height: 24),
                Text(
                  'AI \uD14C\uB2C8\uC2A4 \uCF54\uCE6D\uC744 \uC2DC\uC791\uD558\uC138\uC694',
                  style: textTheme.headlineSmall,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                Text(
                  '\uC2A4\uC719 \uC601\uC0C1\uC744 \uBD84\uC11D\uD574 \uC790\uC138\uB97C \uC774\uD574\uD558\uACE0\n'
                  '\uB354 \uB098\uC740 \uD50C\uB808\uC774\uB97C \uB9CC\uB4E4\uC5B4 \uBCF4\uC138\uC694.',
                  style: textTheme.bodyLarge,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
