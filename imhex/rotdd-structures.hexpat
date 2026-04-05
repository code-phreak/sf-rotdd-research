#pragma author GekySan
#pragma description Game Boy Advance ROM Header

#pragma MIME application/x-gameboy-advance-rom
#pragma MIME application/x-agb-rom
#pragma MIME application/x-gba-rom

import std.string;
import std.mem;
import std.sys;

// In gb.hexpat
namespace format {
    fn licensee_code(str code) {
        match(code) {
            ("00"): return "None";
            ("01" | "31"): return "Nintendo";
            ("08" | "38"): return "Capcom";
            ("09"): return "Hot-B";
            ("0A" | "E0"): return "Jaleco";
            ("0B"): return "Coconuts Japan";
            ("0C" | "6E"): return "Elite Systems";
            ("13" | "69"): return "EA (Electronic Arts)";
            ("18"): return "Hudsonsoft";
            ("19"): return "ITC Entertainment";
            ("1A"): return "Yanoman";
            ("1D"): return "Japan Clary";
            ("1F" | "4A" | "61"): return "Virgin Interactive";
            ("24"): return "PCM Complete";
            ("25"): return "San-X";
            ("28"): return "Kotobuki Systems";
            ("29"): return "Seta";
            ("30" | "70"): return "Infogrames";
            ("32" | "A2" | "B2" | "C4"): return "Bandai";
            ("33"): return "See new licensee code";
            ("34" | "A4"): return "Konami";
            ("35"): return "HectorSoft";
            ("39" | "9D"): return "Banpresto";
            ("3C"): return ".Entertainment i";
            ("3E"): return "Gremlin";
            ("41"): return "Ubisoft";
            ("42" | "EB"): return "Atlus";
            ("44" | "4D"): return "Malibu";
            ("46" | "CF"): return "Angel";
            ("47"): return "Spectrum Holoby";
            ("49"): return "Irem";
            ("4F"): return "U.S. Gold";
            ("50"): return "Absolute";
            ("51" | "B0"): return "Acclaim";
            ("52"): return "Activision";
            ("53"): return "American Sammy";
            ("54"): return "GameTek";
            ("55"): return "Park Place";
            ("56" | "DB" | "FF"): return "LJN";
            ("57"): return "Matchbox";
            ("59"): return "Milton Bradley";
            ("5A"): return "Mindscape";
            ("5B"): return "Romstar";
            ("5C" | "D6"): return "Naxat Soft";
            ("5D"): return "Tradewest";
            ("60"): return "Titus";
            ("67"): return "Ocean Interactive";
            ("6F"): return "Electro Brain";
            ("71"): return "Interplay";
            ("72" | "AA"): return "Broderbund";
            ("73"): return "Sculptered Soft";
            ("75"): return "The Sales Curve";
            ("78"): return "t.hq";
            ("79"): return "Accolade";
            ("7A"): return "Triffix Entertainment";
            ("7C"): return "Microprose";
            ("7F" | "C2"): return "Kemco";
            ("80"): return "Misawa Entertainment";
            ("83"): return "Lozc";
            ("86" | "C4"): return "Tokuma Shoten Intermedia";
            ("8B"): return "Bullet-Proof Software";
            ("8C"): return "Vic Tokai";
            ("8E"): return "Ape";
            ("8F"): return "I'Max";
            ("91"): return "Chunksoft Co.";
            ("92"): return "Video System";
            ("93"): return "Tsubaraya Productions Co.";
            ("95"): return "Varie Corporation";
            ("96"): return "Yonezawa/S'Pal";
            ("97"): return "Kaneko";
            ("99"): return "Arc";
            ("9A"): return "Nihon Bussan";
            ("9B"): return "Tecmo";
            ("9C"): return "Imagineer";
            ("9F"): return "Nova";
            ("A1"): return "Hori Electric";
            ("A6"): return "Kawada";
            ("A7"): return "Takara";
            ("A9"): return "Technos Japan";
            ("AC"): return "Toei Animation";
            ("AD"): return "Toho";
            ("AF"): return "Namco";
            ("B1"): return "ASCII or Nexsoft";
            ("B4"): return "Square Enix";
            ("B6"): return "HAL Laboratory";
            ("B7"): return "SNK";
            ("B9" | "CE"): return "Pony Canyon";
            ("BA"): return "Culture Brain";
            ("BB"): return "Sunsoft";
            ("BD"): return "Sony Imagesoft";
            ("BF"): return "Sammy";
            ("C0" | "D0"): return "Taito";
            ("C3"): return "Squaresoft";
            ("C5"): return "Data East";
            ("C6"): return "Tonkinhouse";
            ("C8"): return "Koei";
            ("C9"): return "UFL";
            ("CA"): return "Ultra";
            ("CB"): return "Vap";
            ("CC"): return "Use Corporation";
            ("CD"): return "Meldac";
            ("D1"): return "Sofel";
            ("D2"): return "Quest";
            ("D3"): return "Sigma Enterprises";
            ("D4"): return "ASK Kodansha Co.";
            ("D7"): return "Copya System";
            ("DA"): return "Tomy";
            ("DD"): return "NCS";
            ("DE"): return "Human";
            ("DF"): return "Altron";
            ("E1"): return "Towa Chiki";
            ("E2"): return "Yutaka";
            ("E3"): return "Varie";
            ("E5"): return "Epoch";
            ("E7"): return "Athena";
            ("E8"): return "Asmik";
            ("E9"): return "Natsume";
            ("EA"): return "King Records";
            ("EC"): return "Epic/Sony Records";
            ("EE"): return "IGS";
            ("F0"): return "A Wave";
            ("F3"): return "Extreme Entertainment";
        }
        return "Unknown Licensee";
    };
}

fn calcChecksum() {
    u8 sum = 0;
    u8 offset = 0xA0;

    while (offset <= 0xBC) {
        sum += std::mem::read_unsigned(offset, 1);
        offset += 1;
    }

    return ((-((0x19 + sum) & 0xFF)) & 0xFF) == std::mem::read_unsigned(0xBD, 1);
};

struct GBAHeader {
    u8 entryPoint[4]       [[comment("ARM entry point code, typically a 'B rom_start' instruction")]];
    u8 nintendoLogo[156]   [[comment("Nintendo logo")]];
    char gameTitle[12]     [[comment("Game title, uppercase ASCII, max 12 characters")]];
    char gameCode[4]       [[comment("Game code, uppercase ASCII, 4 characters")]];
    char makerCode[2]      [[format("format::licensee_code"), comment("Maker code, uppercase ASCII, 2 characters")]];
    u8 fixedValue          [[comment("Fixed value, must be 0x96")]];
    u8 unitCode            [[comment("Main unit code, identifies required hardware (00h for GBA)")]];
    u8 deviceType          [[comment("Device type, usually 00h. Bit 7 relates to DACS/debug features")]];
    u8 reserved1[7]        [[comment("Reserved area, must be zero-filled")]];
    u8 softwareVersion     [[comment("Software version number, usually 00h")]];
    u8 complementCheck     [[comment("Header checksum, required for validation")]];
    u8 reserved2[2]        [[comment("Reserved area, must be zero-filled")]];
};

if (!calcChecksum()) {
    std::error("Checksum validation failed: Calculated value does not match the expected checksum in the header.");
}

GBAHeader gbaHeader @ 0x0000;

struct EnemyEntry {
    u8 Separator [[color("808080")]];
    u8 InventoryItem [[color("663300")]]; // What item they hold in their inventory
    u8 DropChance [[color("FF6666")]]; // Flat Value. IE: 63 = 99% Drop Chance
    u8 SpellList[4] [[color("6699FF")]];    // 16 00 00 00 is Blaze 2. I'm going to guess this a pointer to spell lists. Adding 16 to other mages slots does not give them Blaze 4.
    u8 EnemyID[2] [[color("FFCC00")]];       // This is the enemy ID. The second value does appear to be the level the enemy is but if there isn't a corresponding table entry it defaults to a goblin'
    u8 SpawnLocation[2] [[color("CC66FF")]];     //  The co-ordinates enemies spawn
    u8 Equipment [[color("FF9900")]];     // This changes what they have equipped. 2F = Short Sword. 50 = Middle Axe
};
EnemyEntry SpawnDefinitions[542] @ 0x0056F6F9; // Allows you to customize the parameters of individual enemies placed on maps.

struct EnemyStats {
    u8 EnemyID[2] [[color("FF0000")]]; // Enemy ID. EnemyEntry should always match this
    u8 MovementType [[color("FF8000")]]; // 3F = Flying
    u8 Unknown [[color("FFFF00")]]; // No idea. It's not land effect which seems to attach itself to movement type.
    u8 Health[2] [[color("00FF00")]]; // Second value is for health over 99
    u8 Mana [[color("00CCCC")]];
    u8 Attack [[color("0000FF")]];
    u8 Defense [[color("CC00CC")]];
    u8 Move [[color("CCCC00")]];
    u8 Agility [[color("FFB366")]];
    u8 CritChance [[color("FFFF99")]];
    u8 MagicResist [[color("99FF99")]];
    u8 Unknown2[3] [[color("66FFFF")]]; // These don't appear to be spell lists. They do change on some enemies but I'm not sure why.'
};

const u32 ENEMY_TABLE_BASE = 0x001E1144;
const u32 COUNT = 96;

EnemyStats EnemyStats[COUNT] @ ENEMY_TABLE_BASE;

struct EnemyName {
    u8 data[0x2000] [[color("66FFFF")]];
};

EnemyName EnemyNameStrings @ 0x001DD5B0; // The first entry is GOBLIN. You only have to change the first byte in this list to modify what string it's referencing. 'I don't have an exact length for this table yet. There's a lot here to work through.

struct References {
    u8 data[0x100] [[color("66FFFF")]];
};

References IdentityPointers @ 0x0056EC88; // First entry goblin. B1 -> D9 = Goblin to Dark Dwarf.

struct FirstBattleMaybe {
    u8 data[0x5];
};

FirstBattleMaybe FirstBattle @ 0x001E88E0; // One single byte here changes enemy spawn direction in the first battle. Not sure what else might be doable here?

struct EnemyGraphicsPointers {
    u8 point[2] [[color("FF0066")]];
    u8 zerozero[2] [[color("B3B3B3")]];
};

EnemyGraphicsPointers OverworldSpritePointers[177] @ 0x00003E7C; // The first two bytes decides which sprites to pull for every force member @ enemy type in the game

//40 41 Unpromoted Max
//84 41 Unpromoted Mae
//C8 41 Unpromoted Pelle
//0C 42 Unpromoted Ken
//50 43 Unpromoted Vankar
//94 42 Unpromoted Earnest
//D8 42 Unpromoted Arthur
//1C 43 Unpromoted Gort
//60 43 Unpromoted Luke
//A4 43 Unpromoted Guntz
//E8 43 Unpromoted Anri
//44 44 Unpromoted Alef
//88 44 Unpromoted Tao
//1C 4A Goblin
//30 4A Rune Knight
//6C 4A Dark Dwarf

//38 4F Varios
//4C 4F Elderly Man
//60 4F Elderly Woman
//74 4F Older townsman
//88 4F Older townwoman
//9C 4F Standard Townman
//B0 4F Standard Townwoman
//C4 4F Child Boy
//D8 4F Pink haired child
//EC 4F Dog
//00 50 Cat
//14 50 Chicken
//28 50 Caravan Merchant
//3C 50 Caravan Merchant
//50 50 Act 7 NPC - Pretend to be stupid
//64 50 Priest
//78 50 Guardiana King
//8C 50 Act 7 king?
//A0 50 Not sure which king?
//B4 50 Warrel King
//C8 50 Queen
//DC 50 Some kind of princess?
//F0 50 Shirtless Islander
//04 51 Soldier
//18 51 Injured Soldier
//2C 51 Old Man
//40 51 Prisoner?
//54 51 Random Guard
//68 51 Random Mage
//7C 51 NPC Knight
//90 51 Random Woman
//A4 51 Witch
//B8 51 Boken!
//CC 51 Ormont? Ormus but red
//E0 51 Ormus
//F4 51 Guardiana Advisor
//08 52 Mermaid
//1C 52 Spirit of The Spring
//30 52 Some Kid
//44 52 Blue haired girl
//58 52 Karen I think? Red haired kid
//98 52 Fishing Man
//AC 52 Drowning Max
//C0 52 Sheep
//D4 52 Horse Cart
//38 53 Cart
//60 53 Big Boy Boat
//74 53 Boat -> Maybe a different splash?
//88 53 Boat
//9C 53 Nova
//18 54 Nun

//50 FF 02 08 @ 0002FF40 = Start of battle engine pointers. Trace later
//00068970 = Destroys spells. Trace later.

struct PortraitPointers {
    u8 portraitcode[2] [[color("FF0066")]];
    u8 portraitcall[2] [[color("B3B3B3")]];
};

PortraitPointers PortraitControl[160] @0x00019aCC;
//50 9D Max Swwordsman
//90 90 Vankar
//34 A0 Chest
//54 A0 Blank - These entries are for generic enemy types! You can portrait any generic if you want.
//40 A0 Nova
//28 A0 = Red Haired Child
//1C A0 = Blue Haired Child
//E0 9E = Mawlocke

struct SpellEffectPointers {
    u8 spellid[1] [[color("FF0066")]]; // Appears to change what spells do. If I trace this I might found more spell code.
    u8 useless[7] [[color("B3B3B3")]];
};

SpellEffectPointers SpellEffPoint[26] @0x00013F90;

struct WarpPointers {
    u8 WarpID[1] [[color("FF0066")]];
    u8 useless2[3] [[color("B3B3B3")]];
};

WarpPointers WarpPoints[114] @0x0001CC6C; // A lot of these end up pointing to code, and then tilesets.

struct BattleAnimationsForce {
    u8 ForceBattleAnimeReference[3] [[color("FF0066")]];
    u8 zeroeight[1] [[color("B3B3B3")]];
};

BattleAnimationsForce BattleAnimsForce[33] @0x007c2D4;

struct floortilepointers {
    u8 FloorTilereferences[3] [[color("FF0066")]];
    u8 zeroeight1[1] [[color("B3B3B3")]];
};

floortilepointers FloorTiles[9] @0x0007c23C; //Floor Tiles. You can replace what floor tile gets called at what address here.

struct battlebackgroundpointers {
    u8 BattleBackgroundreferences[3] [[color("FF0066")]];
    u8 zeroeight2[1] [[color("B3B3B3")]];
};

battlebackgroundpointers BattleBackgroundP[25] @0x0007C264; //Battle Background. You can replace what gets called. This isn't a per map/tile replacement. Its total'

struct enemybattleanimations {
    u8 EnemyBattleAnims[3] [[color("FF0066")]];
    u8 zeroeight3[1] [[color("B3B3B3")]];
};

enemybattleanimations EnemyBattleAnimationPointers[64] @0x0007C3F8;  // Enemy Battle Animations.
