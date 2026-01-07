mod launch_monitor;
mod mock_radar;
mod opengolfsim;
mod ops243;
mod shot;

use anyhow::Result;
use clap::Parser;

use launch_monitor::{LaunchMonitor, RadarInterface};
use mock_radar::MockRadar;
use opengolfsim::OpenGolfSimClient;
use ops243::OPS243Radar;

#[derive(Parser, Debug)]
#[command(name = "openlaunch-rs")]
#[command(about = "Golf Launch Monitor (Rust) - Phase 1", long_about = None)]
struct Args {
    /// Serial port (auto-detect if not specified)
    #[arg(short, long)]
    port: Option<String>,

    /// Show live readings
    #[arg(short, long)]
    live: bool,

    /// Show radar info and exit
    #[arg(short, long)]
    info: bool,

    /// Use mock radar (for testing without hardware)
    #[arg(short, long)]
    mock: bool,

    /// Shot interval in seconds for mock mode (auto-generate shots)
    #[arg(long, default_value = "20.0")]
    mock_interval: f64,

    /// Enable OpenGolfSim integration
    #[arg(long)]
    opengolfsim: bool,

    /// OpenGolfSim host (default: localhost)
    #[arg(long, default_value = "localhost")]
    opengolfsim_host: String,

    /// OpenGolfSim port (default: 3111 per OpenGolfSim API docs)
    #[arg(long, default_value = "3111")]
    opengolfsim_port: u16,

    /// Use HTTP instead of TCP for OpenGolfSim
    #[arg(long)]
    opengolfsim_http: bool,
}

fn main() -> Result<()> {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    let args = Args::parse();

    println!("{}", "=".repeat(50));
    println!("  OpenLaunch - Golf Launch Monitor (Rust)");
    if args.mock {
        println!("  Using MOCK Radar (Simulation Mode)");
    } else {
        println!("  Using OPS243-A Doppler Radar");
    }
    println!("{}", "=".repeat(50));
    println!();

    // Connect to radar (real or mock)
    if args.mock {
        let mut radar = MockRadar::new(args.mock_interval, true);
        radar.connect()?;
        radar.configure_for_golf()?;
        let info = radar.get_info()?;
        println!(
            "Connected to: {}",
            info.get("Product").unwrap_or(&"OPS243-MOCK".to_string())
        );
        println!(
            "Firmware: {}",
            info.get("Version").unwrap_or(&"unknown".to_string())
        );
        println!(
            "Mode: {}",
            info.get("Mode").unwrap_or(&"Simulation".to_string())
        );
        println!();

        if args.info {
            println!("Radar Configuration:");
            for (key, value) in &info {
                println!("  {}: {}", key, value);
            }
            return Ok(());
        }

        println!(
            "Mock mode: Auto-generating shots every {:.1} seconds",
            args.mock_interval
        );
        println!("Press Ctrl+C to stop");
        println!();

        // Setup OpenGolfSim integration if enabled
        let opengolfsim_client = if args.opengolfsim {
            let client = OpenGolfSimClient::new(
                args.opengolfsim_host.clone(),
                args.opengolfsim_port,
                args.opengolfsim_http,
            );
            println!(
                "OpenGolfSim integration enabled: {}:{} ({})",
                args.opengolfsim_host,
                args.opengolfsim_port,
                if args.opengolfsim_http { "HTTP" } else { "TCP" }
            );
            println!("Note: If OpenGolfSim is not running, connection errors will be logged as debug messages.");
            Some(client)
        } else {
            None
        };

        // Create launch monitor with mock radar
        let mut monitor = LaunchMonitor::with_opengolfsim(radar, args.live, opengolfsim_client);
        monitor.run()?;
    } else {
        let mut radar = OPS243Radar::new(args.port.clone())?;
        radar.connect()?;
        radar.configure_for_golf()?;
        let info = radar.get_info()?;
        println!(
            "Connected to: {}",
            info.get("Product").unwrap_or(&"OPS243".to_string())
        );
        println!(
            "Firmware: {}",
            info.get("Version").unwrap_or(&"unknown".to_string())
        );
        println!();

        if args.info {
            println!("Radar Configuration:");
            for (key, value) in &info {
                println!("  {}: {}", key, value);
            }
            return Ok(());
        }

        println!("Ready! Swing when ready...");
        println!("Press Ctrl+C to stop");
        println!();

        // Setup OpenGolfSim integration if enabled
        let opengolfsim_client = if args.opengolfsim {
            let client = OpenGolfSimClient::new(
                args.opengolfsim_host.clone(),
                args.opengolfsim_port,
                args.opengolfsim_http,
            );
            println!(
                "OpenGolfSim integration enabled: {}:{} ({})",
                args.opengolfsim_host,
                args.opengolfsim_port,
                if args.opengolfsim_http { "HTTP" } else { "TCP" }
            );
            println!("Note: If OpenGolfSim is not running, connection errors will be logged as debug messages.");
            Some(client)
        } else {
            None
        };

        // Create launch monitor with real radar
        let mut monitor = LaunchMonitor::with_opengolfsim(radar, args.live, opengolfsim_client);
        monitor.run()?;
    }

    Ok(())
}
