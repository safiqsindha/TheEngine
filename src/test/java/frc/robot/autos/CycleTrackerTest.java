package frc.robot.autos;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** Tests for {@link CycleTracker}. Uses a mutable clock for deterministic timing. */
class CycleTrackerTest {

  private double fakeTime = 0.0;
  private CycleTracker tracker;

  @BeforeEach
  void setUp() {
    fakeTime = 0.0;
    tracker = new CycleTracker(() -> fakeTime);
  }

  @Test
  void singleCompleteCycle() {
    fakeTime = 0.0;
    tracker.startCycle();
    assertEquals(CycleTracker.CyclePhase.SEEKING, tracker.getCurrentPhase());

    fakeTime = 2.0;
    tracker.markPickup();
    assertEquals(CycleTracker.CyclePhase.CARRYING, tracker.getCurrentPhase());

    fakeTime = 3.5;
    tracker.markScore();
    assertEquals(CycleTracker.CyclePhase.IDLE, tracker.getCurrentPhase());

    assertEquals(1, tracker.getCycleCount());
    assertEquals(3.5, tracker.getLastCycleTimeSeconds(), 1e-9);
    assertEquals(3.5, tracker.getAverageCycleTimeSeconds(), 1e-9);
  }

  @Test
  void twoCompleteCycles_averageComputed() {
    // First cycle: 0 -> 4s
    fakeTime = 0.0;
    tracker.startCycle();
    fakeTime = 1.0;
    tracker.markPickup();
    fakeTime = 4.0;
    tracker.markScore();

    // Second cycle: 5 -> 11s
    fakeTime = 5.0;
    tracker.startCycle();
    fakeTime = 7.0;
    tracker.markPickup();
    fakeTime = 11.0;
    tracker.markScore();

    assertEquals(2, tracker.getCycleCount());
    assertEquals(6.0, tracker.getLastCycleTimeSeconds(), 1e-9);
    // Average: (4.0 + 6.0) / 2 = 5.0
    assertEquals(5.0, tracker.getAverageCycleTimeSeconds(), 1e-9);
  }

  @Test
  void getCycleCount_beforeAnyCycles_returnsZero() {
    assertEquals(0, tracker.getCycleCount());
  }

  @Test
  void getLastCycleTime_beforeAnyCycles_returnsZero() {
    assertEquals(0.0, tracker.getLastCycleTimeSeconds(), 1e-9);
  }

  @Test
  void incompleteCycle_countStaysZero() {
    tracker.startCycle();
    fakeTime = 2.0;
    tracker.markPickup();
    // No markScore call — cycle never completes.
    assertEquals(0, tracker.getCycleCount());
    assertEquals(CycleTracker.CyclePhase.CARRYING, tracker.getCurrentPhase());
  }

  @Test
  void reset_clearsEverything() {
    // Complete a cycle first.
    tracker.startCycle();
    fakeTime = 1.0;
    tracker.markPickup();
    fakeTime = 2.0;
    tracker.markScore();
    assertEquals(1, tracker.getCycleCount());

    tracker.reset();
    assertEquals(0, tracker.getCycleCount());
    assertEquals(0.0, tracker.getLastCycleTimeSeconds(), 1e-9);
    assertEquals(0.0, tracker.getAverageCycleTimeSeconds(), 1e-9);
    assertEquals(CycleTracker.CyclePhase.IDLE, tracker.getCurrentPhase());
  }

  @Test
  void markScore_withoutStartCycle_noCrash_countStaysZero() {
    // Should be a no-op — phase is IDLE, not CARRYING.
    tracker.markScore();
    assertEquals(0, tracker.getCycleCount());
    assertEquals(CycleTracker.CyclePhase.IDLE, tracker.getCurrentPhase());
  }

  @Test
  void markPickup_withoutStartCycle_noCrash() {
    tracker.markPickup();
    assertEquals(CycleTracker.CyclePhase.IDLE, tracker.getCurrentPhase());
  }

  @Test
  void startCycle_whileAlreadySeeking_ignored() {
    fakeTime = 0.0;
    tracker.startCycle();
    fakeTime = 5.0;
    // Second startCycle should be ignored since we're already SEEKING.
    tracker.startCycle();
    tracker.markPickup();
    fakeTime = 7.0;
    tracker.markScore();
    // Time should be from the first startCycle (t=0) to markScore (t=7).
    assertEquals(7.0, tracker.getLastCycleTimeSeconds(), 1e-9);
  }
}
