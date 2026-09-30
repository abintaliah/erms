import 'package:flutter/material.dart';

class WathiqBrand extends StatelessWidget {
  const WathiqBrand({
    this.name,
    this.showName = true,
    this.markSize = 42,
    this.textStyle,
    super.key,
  });

  final bool showName;
  final String? name;
  final double markSize;
  final TextStyle? textStyle;

  @override
  Widget build(BuildContext context) {
    final mark = CustomPaint(
      key: const ValueKey('wathiq-logo-mark'),
      size: Size(markSize * 5 / 6, markSize),
      painter: const _WathiqMarkPainter(),
    );
    if (!showName) {
      return mark;
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        mark,
        const SizedBox(width: 10),
        Text(
          name ?? '',
          style:
              textStyle ??
              Theme.of(context).textTheme.headlineSmall?.copyWith(
                color: const Color(0xFF0B74C4),
                fontWeight: FontWeight.w700,
              ),
        ),
      ],
    );
  }
}

class _WathiqMarkPainter extends CustomPainter {
  const _WathiqMarkPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 100, size.height / 120);
    _draw(canvas, const Color(0xFF152033), [
      const Offset(14, 22),
      const Offset(43, 49),
      const Offset(41, 75),
      const Offset(17, 95),
      const Offset(0, 65),
    ]);
    _draw(canvas, const Color(0xFF2E9DDA), [
      const Offset(56, 0),
      const Offset(92, 34),
      const Offset(71, 55),
      const Offset(47, 49),
      const Offset(41, 23),
    ]);
    _draw(canvas, const Color(0xFFF4B63D), [
      const Offset(72, 52),
      const Offset(100, 41),
      const Offset(81, 92),
    ]);
    _draw(canvas, const Color(0xFFDBF3FD), [
      const Offset(17, 88),
      const Offset(43, 63),
      const Offset(53, 72),
      const Offset(65, 118),
      const Offset(34, 111),
    ]);
    _draw(canvas, const Color(0xFF152033), [
      const Offset(51, 76),
      const Offset(71, 87),
      const Offset(61, 120),
    ]);
    canvas.restore();
  }

  void _draw(Canvas canvas, Color color, List<Offset> points) {
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (final point in points.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    path.close();
    canvas.drawPath(path, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
