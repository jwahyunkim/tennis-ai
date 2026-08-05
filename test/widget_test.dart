import 'package:flutter_test/flutter_test.dart';
import 'package:tennis_ai/app/tennis_ai_app.dart';

void main() {
  testWidgets('shows the Tennis AI home screen', (tester) async {
    await tester.pumpWidget(const TennisAiApp());

    expect(find.text('Tennis AI'), findsOneWidget);
    expect(
      find.text(
        'AI \uD14C\uB2C8\uC2A4 \uCF54\uCE6D\uC744 \uC2DC\uC791\uD558\uC138\uC694',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('\uC2A4\uC719 \uC601\uC0C1\uC744 \uBD84\uC11D\uD574'),
      findsOneWidget,
    );
  });
}
