import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:model_viewer_plus/model_viewer_plus.dart';
import 'package:tennis_ai/core/api_client.dart';
import 'package:tennis_ai/core/presentation/async_feedback.dart';
import 'package:tennis_ai/features/videos/application/video_controllers.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';

class ModelResultView extends ConsumerWidget {
  const ModelResultView({required this.model, super.key});
  final BodyModel model;

  @override
  Widget build(BuildContext context, WidgetRef ref) => ref
      .watch(modelFileProvider(model))
      .when(
        loading: () => const SizedBox(
          height: 260,
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('3D 모델을 불러오고 있습니다.'),
              ],
            ),
          ),
        ),
        error: (error, stack) => ErrorFeedback(
          error: error,
          onRetry: () => ref.invalidate(modelFileProvider(model)),
        ),
        data: (file) => _ModelRenderer(
          key: ValueKey(file.uri),
          uri: file.uri,
          onRetry: () => ref.invalidate(modelFileProvider(model)),
        ),
      );
}

class _ModelRenderer extends StatefulWidget {
  const _ModelRenderer({required this.uri, required this.onRetry, super.key});
  final String uri;
  final VoidCallback onRetry;

  @override
  State<_ModelRenderer> createState() => _ModelRendererState();
}

class _ModelRendererState extends State<_ModelRenderer> {
  bool _failed = false;
  bool _loaded = false;
  Timer? _timeout;

  @override
  void initState() {
    super.initState();
    _timeout = Timer(const Duration(seconds: 45), () {
      if (mounted && !_loaded) setState(() => _failed = true);
    });
  }

  @override
  void dispose() {
    _timeout?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_failed) {
      return ErrorFeedback(
        error: const AppException(
          'model_render',
          '3D 모델을 표시하지 못했습니다. 다시 불러와 주세요.',
        ),
        onRetry: widget.onRetry,
      );
    }
    return Column(
      children: [
        SizedBox(
          height: 380,
          child: Stack(
            children: [
              ModelViewer(
                src: widget.uri,
                alt: '이 영상에서 생성된 나의 3D 모델',
                ar: false,
                autoRotate: false,
                autoPlay: true,
                cameraControls: true,
                backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
                debugLogging: false,
                relatedJs: '''
const viewer = document.querySelector('model-viewer');
viewer.addEventListener('load', () => ModelStatus.postMessage('loaded'));
viewer.addEventListener('error', () => ModelStatus.postMessage('error'));
''',
                javascriptChannels: {
                  JavascriptChannel(
                    'ModelStatus',
                    onMessageReceived: (message) {
                      if (!mounted) return;
                      if (message.message == 'loaded') {
                        _timeout?.cancel();
                        setState(() => _loaded = true);
                      } else if (message.message == 'error') {
                        _timeout?.cancel();
                        setState(() => _failed = true);
                      }
                    },
                  ),
                },
              ),
              if (!_loaded) const Center(child: CircularProgressIndicator()),
            ],
          ),
        ),
        const SizedBox(height: 8),
        const Text('드래그하여 회전하고 두 손가락으로 확대해 보세요.'),
      ],
    );
  }
}
