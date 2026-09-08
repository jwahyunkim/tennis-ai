import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tennis_ai/core/presentation/async_feedback.dart';
import 'package:tennis_ai/features/videos/application/video_controllers.dart';
import 'package:tennis_ai/features/videos/domain/video.dart';
import 'package:video_player/video_player.dart';

class OriginalVideoPlayer extends ConsumerWidget {
  const OriginalVideoPlayer({required this.videoId, super.key});
  final String videoId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref
        .watch(videoPlaybackProvider(videoId))
        .when(
          loading: () => const SizedBox(
            height: 180,
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (error, stack) => ErrorFeedback(
            error: error,
            onRetry: () => ref.invalidate(videoPlaybackProvider(videoId)),
          ),
          data: (source) => _Player(key: ValueKey(source), source: source),
        );
  }
}

class _Player extends StatefulWidget {
  const _Player({required this.source, super.key});
  final PlaybackSource source;
  @override
  State<_Player> createState() => _PlayerState();
}

class _PlayerState extends State<_Player> with WidgetsBindingObserver {
  late VideoPlayerController _controller;
  late Future<void> _initialization;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initialize();
  }

  void _initialize() {
    _controller = VideoPlayerController.networkUrl(
      widget.source.uri,
      httpHeaders: widget.source.headers,
    );
    _initialization = _controller.initialize();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) _controller.pause();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<void>(
    future: _initialization,
    builder: (context, snapshot) {
      if (snapshot.hasError) return _failure();
      if (snapshot.connectionState != ConnectionState.done) {
        return const SizedBox(
          height: 180,
          child: Center(child: CircularProgressIndicator()),
        );
      }
      return ValueListenableBuilder<VideoPlayerValue>(
        valueListenable: _controller,
        builder: (context, value, child) {
          if (value.hasError) return _failure();
          return Column(
            children: [
              ColoredBox(
                color: Colors.black,
                child: AspectRatio(
                  aspectRatio: value.aspectRatio > 0
                      ? value.aspectRatio
                      : 16 / 9,
                  child: VideoPlayer(_controller),
                ),
              ),
              VideoProgressIndicator(
                _controller,
                allowScrubbing: true,
                padding: const EdgeInsets.symmetric(vertical: 12),
              ),
              Row(
                children: [
                  IconButton(
                    tooltip: value.isPlaying ? '일시정지' : '재생',
                    onPressed: () async {
                      if (value.isPlaying) {
                        await _controller.pause();
                      } else {
                        if (value.position >= value.duration) {
                          await _controller.seekTo(Duration.zero);
                        }
                        await _controller.play();
                      }
                    },
                    icon: Icon(
                      value.isPlaying ? Icons.pause : Icons.play_arrow,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      '${_duration(value.position)} / ${_duration(value.duration)}',
                    ),
                  ),
                  IconButton(
                    tooltip: value.volume > 0 ? '음소거' : '소리 켜기',
                    onPressed: () =>
                        _controller.setVolume(value.volume > 0 ? 0 : 1),
                    icon: Icon(
                      value.volume > 0
                          ? Icons.volume_up_outlined
                          : Icons.volume_off_outlined,
                    ),
                  ),
                ],
              ),
            ],
          );
        },
      );
    },
  );

  Widget _failure() => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          const Icon(Icons.videocam_off_outlined, size: 36),
          const SizedBox(height: 8),
          const Text(
            '영상을 재생하지 못했습니다. 연결 상태와 영상 형식을 확인해 주세요.',
            textAlign: TextAlign.center,
          ),
          TextButton(
            onPressed: () {
              _controller.dispose();
              setState(_initialize);
            },
            child: const Text('재생 다시 시도'),
          ),
        ],
      ),
    ),
  );

  String _duration(Duration value) =>
      '${value.inMinutes}:${(value.inSeconds % 60).toString().padLeft(2, '0')}';
}
