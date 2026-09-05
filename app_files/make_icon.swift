import AppKit

let size = NSSize(width: 1024, height: 1024)
let image = NSImage(size: size)
image.lockFocus()

let outer = NSBezierPath(roundedRect: NSRect(x: 52, y: 52, width: 920, height: 920), xRadius: 218, yRadius: 218)
let gradient = NSGradient(colors: [
    NSColor(calibratedRed: 0.08, green: 0.10, blue: 0.23, alpha: 1),
    NSColor(calibratedRed: 0.19, green: 0.10, blue: 0.42, alpha: 1),
    NSColor(calibratedRed: 0.03, green: 0.45, blue: 0.55, alpha: 1)
])!
gradient.draw(in: outer, angle: -48)

NSGraphicsContext.current?.saveGraphicsState()
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.36)
shadow.shadowBlurRadius = 34
shadow.shadowOffset = NSSize(width: 0, height: -20)
shadow.set()
let monitor = NSBezierPath(roundedRect: NSRect(x: 190, y: 274, width: 644, height: 470), xRadius: 62, yRadius: 62)
NSColor.white.withAlphaComponent(0.96).setFill()
monitor.fill()
NSGraphicsContext.current?.restoreGraphicsState()

let screen = NSBezierPath(roundedRect: NSRect(x: 236, y: 322, width: 552, height: 374), xRadius: 34, yRadius: 34)
NSColor(calibratedWhite: 0.055, alpha: 1).setFill()
screen.fill()

let glow = NSShadow()
glow.shadowColor = NSColor(calibratedRed: 0.18, green: 0.96, blue: 0.82, alpha: 0.9)
glow.shadowBlurRadius = 22
glow.shadowOffset = .zero
glow.set()

let points: [(CGFloat, CGFloat)] = [
    (275, 495), (320, 495), (350, 573), (390, 419), (430, 610),
    (474, 468), (520, 548), (565, 448), (610, 581), (655, 494), (748, 494)
]
let wave = NSBezierPath()
wave.move(to: NSPoint(x: points[0].0, y: points[0].1))
for p in points.dropFirst() { wave.line(to: NSPoint(x: p.0, y: p.1)) }
wave.lineWidth = 20
wave.lineCapStyle = .round
wave.lineJoinStyle = .round
NSColor(calibratedRed: 0.20, green: 0.96, blue: 0.80, alpha: 1).setStroke()
wave.stroke()

NSShadow().set()
let stand = NSBezierPath(roundedRect: NSRect(x: 445, y: 197, width: 134, height: 94), xRadius: 30, yRadius: 30)
NSColor.white.withAlphaComponent(0.96).setFill()
stand.fill()
let foot = NSBezierPath(roundedRect: NSRect(x: 350, y: 170, width: 324, height: 62), xRadius: 31, yRadius: 31)
foot.fill()

image.unlockFocus()
let data = image.tiffRepresentation!
let rep = NSBitmapImageRep(data: data)!
let png = rep.representation(using: .png, properties: [:])!
try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
