import 'package:tennis_ai/features/videos/domain/video.dart';

String videoStatusLabel(TennisVideo video) => switch (video.job?.status) {
  'queued' => '영상 확인 대기',
  'processing' => '영상 확인 중',
  'awaiting_model' => '영상 확인 완료 · 3D 생성 준비 중',
  'succeeded' => '3D 모델 생성 완료',
  'failed' => '영상 처리 실패',
  'cancelled' => '작업 취소됨',
  _ => video.status == 'failed' ? '영상 확인 실패' : '영상 업로드 완료',
};

String jobErrorLabel(String? code) => switch (code) {
  'invalid_video' => '영상을 읽을 수 없습니다. 재생 가능한 MP4 또는 MOV 파일을 다시 올려 주세요.',
  'video_too_long' => '영상 길이가 업로드 기준을 초과했습니다. 짧게 편집한 영상을 올려 주세요.',
  'processing_unavailable' => '영상 확인 서비스에 연결하지 못했습니다. 다시 시도해 주세요.',
  'worker_interrupted' => '처리가 중단되었습니다. 다시 시도해 주세요.',
  'unsupported_resolution' => '지원하는 해상도를 초과했습니다. 4K 이하 영상을 올려 주세요.',
  'invalid_model_artifact' => '3D 결과 파일을 확인하지 못했습니다. 다시 시도해 주세요.',
  'model_unavailable' => '3D 모델 생성 기능이 준비 중입니다.',
  _ => '영상 처리 중 문제가 발생했습니다. 다시 시도하거나 다른 영상을 올려 주세요.',
};

String formatBytes(int bytes) =>
    '${(bytes / 1024 / 1024).toStringAsFixed(1)} MB';

String formatDate(DateTime value) {
  final date = value.toLocal();
  return '${date.year}.${date.month.toString().padLeft(2, '0')}.${date.day.toString().padLeft(2, '0')}';
}
