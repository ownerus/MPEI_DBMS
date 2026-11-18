use clap::Parser;
use mpei_dbms::cli::{Cli, Commands};
use std::process;

fn main() {
    let cli = Cli::parse();
    let db_path = cli.db.clone().unwrap_or_else(mpei_dbms::database::get_default_db_path);

    // If explicit subcommand other than Gui is requested, run CLI
    match &cli.command {
        Some(Commands::Report(_))
        | Some(Commands::Finance(_))
        | Some(Commands::Projects(_))
        | Some(Commands::Sync) => {
            if let Err(e) = mpei_dbms::cli::run_cli_command(&cli, &db_path) {
                eprintln!("Ошибка выполнения команды: {}", e);
                process::exit(1);
            }
        }
        Some(Commands::Gui) | None => {
            // Launch GUI
            if let Err(e) = mpei_dbms::gui::run_gui(db_path) {
                eprintln!("Ошибка запуска графического интерфейса: {}", e);
                process::exit(1);
            }
        }
    }
}
