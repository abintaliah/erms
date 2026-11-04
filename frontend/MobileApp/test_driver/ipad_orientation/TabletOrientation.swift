import XCTest

final class TabletOrientation: XCTestCase {
    func testLandscape() {
        XCUIDevice.shared.orientation = .landscapeLeft
        XCTAssertEqual(XCUIDevice.shared.orientation, .landscapeLeft)
    }
}
